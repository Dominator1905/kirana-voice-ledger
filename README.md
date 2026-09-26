# 📱 KhataManager Pro - AI-Powered Voice Ledger

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)
![Gemini AI](https://img.shields.io/badge/Google_Gemini-8E75B2?style=for-the-badge&logo=google&logoColor=white)

An intelligent, voice-first Progressive Web App (PWA) designed to modernize transaction tracking for local shopkeepers and Kirana stores. Built for the **OpenAI Club Hackathon at Thakur College of Engineering and Technology (TCET)**.

---

## 🎯 The Problem
Local shopkeepers (like the local *Paan Bhandar* or *Kirana* store) lose track of small credit transactions ("Udhar") during rush hours because manually writing them down in a physical diary is too slow. Existing digital ledger apps require typing, which introduces friction for users who are busy or less tech-savvy.

## 💡 The Solution
**KhataManager Pro** eliminates typing entirely. Shopkeepers can simply tap a microphone and speak naturally (e.g., *"Ramesh ko 50 rupaye ka doodh udhar diya"*), or snap a picture of a physical receipt. The Google Gemini AI automatically extracts the customer name, amount, items, and transaction type, instantly updating a centralized cloud database.

---

## ✨ Key Features

*   🎙️ **Voice-to-Ledger (Gemini AI):** Natural language processing extracts structured data from casual voice notes.
*   📸 **Smart Receipt Scanning:** OCR and AI parsing to log physical bills instantly.
*   🔄 **Failsafe API Rotation:** Engineered with a custom multi-key fallback system. If the primary AI API key hits a rate limit during high traffic, the backend silently and automatically routes to backup keys to ensure 100% uptime.
*   📅 **Smart Date Bifurcation:** Transactions are automatically grouped by date (Today, Yesterday, etc.) with sticky scrolling.
*   💎 **Premium Glassmorphism UI:** A sleek, modern, and highly responsive interface built with Tailwind CSS.
*   📱 **PWA Ready:** Fully installable as a native mobile app directly from the browser for a full-screen experience.
*   📊 **One-Click Export:** Download full ledger history as a CSV file for auditing.
*   💬 **WhatsApp Integration:** Auto-generated payment reminder messages for customers with pending balances.

---

## 🛠️ Tech Stack

*   **Frontend:** HTML5, Vanilla JavaScript, Tailwind CSS (Glassmorphism Theme)
*   **Backend:** Python, FastAPI
*   **Artificial Intelligence:** Google Gemini API (3.6 Flash Model)
*   **Database:** Supabase (PostgreSQL)
*   **Deployment:** Render (Backend/API) & GitHub

---

## 🚀 System Architecture

1.  **Client:** The PWA records audio via `MediaRecorder` or captures images via the device camera.
2.  **API Gateway:** FastAPI receives the binary data via `multipart/form-data`.
3.  **AI Processing:** The payload is sent to Gemini AI alongside a strict system prompt to enforce a structured JSON response. Failsafe routing ensures completion.
4.  **Database Sync:** The parsed JSON data is validated and inserted into Supabase.
5.  **UI Update:** The frontend pulls the live sync and injects the new transaction into the DOM with fluid animations.

---

## 💻 Local Installation & Setup

Follow these steps to run the project locally on your machine.

### Prerequisites
* Python 3.9+
* A Supabase Account & Project
* Google Gemini API Keys

* ### for LOGIN
* USE 00000 00000
* PASSWORD  0000

### 1. Clone the Repository
```bash
git clone [https://github.com/your-username/kirana-voice-ledger.git](https://github.com/your-username/kirana-voice-ledger.git)
cd kirana-voice-ledger
