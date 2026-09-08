import os
import json
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from google.genai import types
import traceback

# Load environment variables
load_dotenv()

app = FastAPI()

# --- SUPABASE SETUP ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- GEMINI KEY ROTATION SETUP ---
# It will look for 'GEMINI_API_KEYS' (plural, comma-separated) or fallback to the old 'GEMINI_API_KEY'
keys_string = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
API_KEYS = [k.strip() for k in keys_string.split(",") if k.strip()]

if not API_KEYS:
    raise ValueError("Missing Gemini API Keys. Please set GEMINI_API_KEYS.")

# Global variable to keep track of which key we are currently using
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
            # Initialize client with the current active key
            client = genai.Client(api_key=active_key)
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    prompt
                ]
            )
            return response.text.strip()
            
        except Exception as e:
            error_message = str(e).lower()
            # If the error is about quota/limits (429), rotate the key
            if "429" in error_message or "quota" in error_message or "exhausted" in error_message:
                print(f"Key #{current_key_index + 1} is exhausted! Switching keys...")
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                attempts += 1
            else:
                # If it's a different kind of error, stop and raise it
                raise e
                
    # If the loop finishes, it means ALL keys are dead
    raise Exception("ALL API KEYS HAVE EXHAUSTED THEIR QUOTAS!")


# --- MODELS ---
class ManualTransaction(BaseModel):
    customer_name: str
    amount: float
    transaction_type: str

# --- ROUTES ---
@app.get("/")
async def serve_frontend():
    return FileResponse("index.html")

# --- NEW PWA ROUTES ---
@app.get("/manifest.json")
async def get_manifest():
    return FileResponse("manifest.json")

@app.get("/sw.js")
async def get_sw():
    return FileResponse("sw.js")
# ----------------------

@app.get("/transactions")
async def get_transactions():
    try:
        response = supabase.table("transactions").select("*").order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/add-transaction")
async def add_transaction(transaction: ManualTransaction):
    data = {
        "customer_name": transaction.customer_name,
        "amount": transaction.amount,
        "transaction_type": transaction.transaction_type,
        "items_purchased": ["Manual Entry"]
    }
    try:
        response = supabase.table("transactions").insert(data).execute()
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str):
    try:
        supabase.table("transactions").delete().eq("id", transaction_id).execute()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract-audio")
async def extract_audio(audio_file: UploadFile = File(...)):
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
        
        # Round decimals to whole numbers for Supabase
        if "amount" in transaction_data:
            transaction_data["amount"] = int(round(float(transaction_data["amount"])))
        
        db_response = supabase.table("transactions").insert(transaction_data).execute()
        return db_response.data[0]
        
    except Exception as e:
        print(f"AUDIO ERROR: {str(e)}")
        traceback.print_exc() 
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract-receipt")
async def extract_receipt(receipt_image: UploadFile = File(...)):
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
        
        # Round decimals to whole numbers for Supabase
        if "amount" in transaction_data:
            transaction_data["amount"] = int(round(float(transaction_data["amount"])))
        
        db_response = supabase.table("transactions").insert(transaction_data).execute()
        return db_response.data[0]
        
    except Exception as e:
        print(f"RECEIPT ERROR: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
