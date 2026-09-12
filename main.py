import os
import json
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from google.genai import types
import traceback

# Load environment variables
load_dotenv()

app = FastAPI(title="Smart-Budget AI Support Agent")

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SUPABASE SETUP ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- GEMINI KEY ROTATION SETUP ---
keys_string = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
API_KEYS = [k.strip() for k in keys_string.split(",") if k.strip()]

if not API_KEYS:
    raise ValueError("Missing Gemini API Keys. Please set GEMINI_API_KEYS.")

current_key_index = 0

def ask_gemini_with_rotation(prompt, file_bytes, mime_type):
    """Tries to ask Gemini. If the key is exhausted, it rotates to the next one."""
    global current_key_index
    attempts = 0
    max_attempts = len(API_KEYS)
    
    while attempts < max_attempts:
        active_key = API_KEYS[current_key_index]
        print(f"Trying API Key #{current_key_index + 1}...")
        
        try:
            client = genai.Client(api_key=active_key)
            response = client.models.generate_content(
                model='gemini-3.6-flash', # Corrected model name
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    prompt
                ]
            )
            return response.text.strip()
            
        except Exception as e:
            error_message = str(e).lower()
            if "429" in error_message or "quota" in error_message or "exhausted" in error_message:
                print(f"Key #{current_key_index + 1} is exhausted! Switching keys...")
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                attempts += 1
            else:
                raise e
                
    raise Exception("ALL API KEYS HAVE EXHAUSTED THEIR QUOTAS!")


# --- MODELS ---
class ManualTransaction(BaseModel):
    customer_name: str
    amount: float
    transaction_type: str

class LoginRequest(BaseModel):
    phone_number: str
    pin: str


# --- FRONTEND & PWA ROUTES ---
@app.get("/")
async def serve_frontend():
    return FileResponse("index.html")

@app.get("/manifest.json")
async def get_manifest():
    return FileResponse("manifest.json")

@app.get("/sw.js")
async def get_sw():
    return FileResponse("sw.js")


# --- AUTHENTICATION ROUTES ---
@app.post("/auth/fallback")
async def fallback_login(req: LoginRequest):
    try:
        response = supabase.table("vendors").select("*").eq("phone_number", req.phone_number).eq("pin", req.pin).execute()
        if not response.data:
            raise HTTPException(status_code=401, detail="Invalid phone number or PIN")
        return {"status": "success", "vendor": response.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/voice")
async def voice_login(audio: UploadFile = File(...)):
    try:
        audio_bytes = await audio.read()
        incoming_type = audio.content_type or ""
        safe_mime_type = "audio/mp4" if "mp4" in incoming_type else "audio/webm"
        
        prompt = """
        Listen to this audio. The user is a shopkeeper stating their shop name and a 4-digit passcode.
        Extract the information and return ONLY a raw JSON object.
        JSON format:
        {
          "shop_name": "extracted shop name",
          "pin": "extracted 4-digit pin"
        }
        """
        
        result_text = ask_gemini_with_rotation(prompt, audio_bytes, safe_mime_type)
        
        # Parse JSON safely
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].strip()
            
        extracted = json.loads(result_text)
        shop_name = extracted.get("shop_name", "")
        pin = str(extracted.get("pin", ""))
        
        # Authenticate against DB
        response = supabase.table("vendors").select("*").ilike("shop_name", f"%{shop_name}%").eq("pin", pin).execute()
        
        if not response.data:
            raise HTTPException(status_code=401, detail=f"Voice auth failed: Match not found for {shop_name}.")
            
        return {
            "status": "success", 
            "method": "voice",
            "vendor": response.data[0],
            "extracted_debug": extracted
        }
    except Exception as e:
        print(f"AUTH AUDIO ERROR: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# --- LEDGER / TRANSACTION ROUTES ---
@app.get("/transactions")
async def get_transactions(x_vendor_phone: str = Header(None)):
    if not x_vendor_phone:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing vendor phone")
    try:
        # FILTER: Only get transactions matching this vendor's phone number
        response = supabase.table("transactions").select("*").eq("vendor_phone", x_vendor_phone).order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/add-transaction")
async def add_transaction(transaction: ManualTransaction, x_vendor_phone: str = Header(None)):
    if not x_vendor_phone:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing vendor phone")
        
    data = {
        "customer_name": transaction.customer_name,
        "amount": transaction.amount,
        "transaction_type": transaction.transaction_type,
        "items_purchased": ["Manual Entry"],
        "vendor_phone": x_vendor_phone # TAG IT: Connect transaction to vendor
    }
    try:
        response = supabase.table("transactions").insert(data).execute()
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str, x_vendor_phone: str = Header(None)):
    if not x_vendor_phone:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        # SECURITY: Ensure they can only delete their own transactions
        supabase.table("transactions").delete().eq("id", transaction_id).eq("vendor_phone", x_vendor_phone).execute()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract-audio")
async def extract_audio(audio_file: UploadFile = File(...), x_vendor_phone: str = Header(None)):
    if not x_vendor_phone:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    try:
        audio_bytes = await audio_file.read()
        incoming_type = audio_file.content_type or ""
        safe_mime_type = "audio/mp4" if "mp4" in incoming_type else "audio/webm"
        
        prompt = """
        Listen to this audio transaction. Extract the following details and return ONLY a raw JSON object.
        - customer_name: Name of the customer
        - amount: Total amount as a number
        - transaction_type: "credit" (if it's udhar/unpaid/credit) or "paid" (if it's jama/paid/cash)
        - items_purchased: List of strings of items mentioned
        
        JSON format:
        {
          "customer_name": "string",
          "amount": 0,
          "transaction_type": "string",
          "items_purchased": ["string"]
        }
        """
        
        result_text = ask_gemini_with_rotation(prompt, audio_bytes, safe_mime_type)
        
        # Parse JSON
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].strip()
            
        transaction_data = json.loads(result_text)
        
        if "amount" in transaction_data:
            transaction_data["amount"] = int(round(float(transaction_data["amount"])))
            
        # TAG IT: Connect the AI extracted transaction to the vendor
        transaction_data["vendor_phone"] = x_vendor_phone
        
        db_response = supabase.table("transactions").insert(transaction_data).execute()
        return db_response.data[0]
        
    except Exception as e:
        print(f"AUDIO ERROR: {str(e)}")
        traceback.print_exc() 
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract-receipt")
async def extract_receipt(receipt_image: UploadFile = File(...), x_vendor_phone: str = Header(None)):
    if not x_vendor_phone:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    try:
        image_bytes = await receipt_image.read()
        mime_type = receipt_image.content_type or "image/jpeg"
        
        prompt = """
        Analyze this receipt, bill, or handwritten ledger note. Extract the following details and return ONLY a raw JSON object.
        - customer_name: Name of the customer (if not found, use "Walk-in Customer")
        - amount: Total amount as a number
        - transaction_type: "paid" (if it looks like a standard cash receipt or bill) or "credit" (if it mentions udhar, due, balance, or unpaid). If unsure, default to "paid".
        - items_purchased: List of strings of items mentioned
        
        JSON format:
        {
          "customer_name": "string",
          "amount": 0,
          "transaction_type": "string",
          "items_purchased": ["string"]
        }
        """
        
        result_text = ask_gemini_with_rotation(prompt, image_bytes, mime_type)
        
        # Parse JSON
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].strip()
            
        transaction_data = json.loads(result_text)
        
        if "amount" in transaction_data:
            transaction_data["amount"] = int(round(float(transaction_data["amount"])))
            
        # TAG IT: Connect the AI extracted receipt to the vendor
        transaction_data["vendor_phone"] = x_vendor_phone
        
        db_response = supabase.table("transactions").insert(transaction_data).execute()
        return db_response.data[0]
        
    except Exception as e:
        print(f"RECEIPT ERROR: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
