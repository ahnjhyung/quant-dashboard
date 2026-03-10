import os
import requests
import json

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyA6OXyOp50TAIr4SskaCV3Kzal9mQmP5qg")
SUPABASE_URL = "https://fcuenflxkkpyplehsizg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZjdWVuZmx4a2tweXBsZWhzaXpnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2OTUxNTk2OCwiZXhwIjoyMDg1MDkxOTY4fQ.Ic-Hc8j67bkYsUKTmcbwh5RwjI84PNS6W75lkW_bnEs"

print("--- 1. Testing Gemini Models ---")
try:
    res = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}")
    if res.status_code == 200:
        models = res.json().get('models', [])
        embed_models = [m['name'] for m in models if 'embedContent' in m.get('supportedGenerationMethods', [])]
        print("Available Embedding Models:", embed_models)
    else:
        print("Gemini Error:", res.text)
except Exception as e:
    print("Gemini Request Error:", e)

print("\n--- 2. Testing Supabase Schema for news_sentiment ---")
try:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    res = requests.get(f"{SUPABASE_URL}/rest/v1/news_sentiment?select=*&limit=1", headers=headers)
    if res.status_code == 200:
        data = res.json()
        if len(data) > 0:
            print("Columns in news_sentiment:", list(data[0].keys()))
        else:
            print("Table empty, cannot infer schema from this endpoint easily. Wait, let's try OPTIONS.")
            res_opt = requests.options(f"{SUPABASE_URL}/rest/v1/news_sentiment", headers=headers)
            print("OPTIONS success. Try to see if swagger is available?")
except Exception as e:
    print("Supabase Request Error:", e)

print("\n--- 3. Testing Supabase Schema for macro_indicators ---")
try:
    res = requests.get(f"{SUPABASE_URL}/rest/v1/macro_indicators?select=*&limit=1", headers=headers)
    if res.status_code == 200:
        data = res.json()
        if len(data) > 0:
            print("Columns in macro_indicators:", list(data[0].keys()))
        else:
            print("Table empty.")
except Exception as e:
    print("Supabase Request Error:", e)
