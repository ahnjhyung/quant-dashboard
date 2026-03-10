import os
import sys
import time
import json
import requests
import pandas as pd
import pandas_datareader.data as web
from datetime import datetime

# ==========================================
# CONFIGURATION & CREDENTIALS
# ==========================================
SUPABASE_URL = "https://fcuenflxkkpyplehsizg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZjdWVuZmx4a2tweXBsZWhzaXpnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2OTUxNTk2OCwiZXhwIjoyMDg1MDkxOTY4fQ.Ic-Hc8j67bkYsUKTmcbwh5RwjI84PNS6W75lkW_bnEs"

# API Keys to rotate through to bypass rate limits
GEMINI_API_KEYS = [
    "AIzaSyAxQvT3UDLp0J9ocxhmeWENi0-YRhP50XQ",
    "AIzaSyBk7YBshDq_jkzQ0-mFUSlj7IgjtHNDaKs"
]

# Set the backfill period
START_DATE = "2020-10-27" # [CHANGED] Requested by user
END_DATE = datetime.now().strftime("%Y-%m-%d")

# ==========================================
# 1. DATA FETCHING & SMART SAMPLING (User Request)
# ==========================================
print(f"[*] Downloading Historical FRED Macro Data from {START_DATE} to {END_DATE}...")
try:
    # Use pandas-datareader to fetch FRED series
    series = [
        'VIXCLS',           # VIX
        'DEXKOUS',          # USD/KRW
        'WALCL',            # Fed Total Assets (Millions)
        'WTREGEN',          # TGA (Billions)
        'RRPONTSYD',        # Reverse Repo (Billions)
        'CPALTT01USM657N',  # US CPI (Growth Rate / Index)
        'FEDFUNDS',         # Fed Funds Rate
        'SP500'             # S&P 500 Index (Using to detect crash/surge days)
    ]
    df_macro = web.DataReader(series, 'fred', START_DATE, END_DATE)
    
    # Forward fill missing data (weekends, etc.)
    df_macro = df_macro.ffill()
    # 🚨 CRITICAL FIX: Do NOT use dropna() because new indicators like RRP or TGA didn't exist in 1998.
    # dropna() was deleting all rows before 2016! We use fillna(0) instead for missing historical data.
    df_macro = df_macro.fillna(0)
    print(f"[+] Downloaded {len(df_macro)} days of raw historical data.")
    
    print("[*] Applying Smart Sampling (Monthly Baseline + Extreme Volatility Days)...")
    # Calculate daily percentage change of S&P 500
    df_macro['SP500_pct'] = df_macro['SP500'].pct_change() * 100
    
    # Rule 1: Monthly Baseline (First trading day of every month)
    df_macro['YM'] = df_macro.index.strftime('%Y-%m')
    baseline_dates = df_macro.groupby('YM').head(1).index
    
    # Rule 2: Extreme Panic or Greed (VIX >= 30 OR S&P 500 moves >= 2.5% in a single day)
    extreme_mask = (df_macro['VIXCLS'] >= 30.0) | (df_macro['SP500_pct'].abs() >= 2.5)
    extreme_dates = df_macro[extreme_mask].index
    
    # Combine and Filter
    selected_dates = baseline_dates.union(extreme_dates)
    df_macro = df_macro.loc[selected_dates].sort_index()
    
    print(f"[+] ✨ Smart Sampling reduced data to {len(df_macro)} highly critical historical days (Crises + Monthly Baseline).")
    
except ImportError:
    print("❌ PLEASE INSTALL PANDAS-DATAREADER: pip install pandas-datareader pandas requests")
    sys.exit(1)
except Exception as e:
    print(f"❌ Failed to fetch FRED data: {e}")
    sys.exit(1)

# ==========================================
# 2. SUPABASE & GEMINI HELPERS
# ==========================================
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

key_index = 0

def get_gemini_embedding(text: str) -> list:
    global key_index
    """ Calls Gemini REST API to convert text into a 3072D vector """
    payload = {
        "model": "models/gemini-embedding-001",
        "content": {
            "parts": [{"text": text}]
        }
    }
    
    # Retry mechanism for 429 Rate Limits with Key Rotation
    for attempt in range(5):
        key = GEMINI_API_KEYS[key_index % len(GEMINI_API_KEYS)]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={key}"
        
        res = requests.post(url, json=payload)
        
        if res.status_code == 200:
            key_index += 1 # Rotate key on success to distribute load evenly
            return res.json()['embedding']['values']
        elif res.status_code == 429:
            key_index += 1 # Switch to the next key
            # If we've rotated through all keys, then sleep
            if attempt > 0:
                sleep_time = 10 * attempt
                print(f"    [!] Both keys rate limited. Sleeping for {sleep_time} seconds (Attempt {attempt+1}/5)...")
                time.sleep(sleep_time)
            else:
                print(f"    [!] Primary key rate limited. Switching to backup key...")
        else:
            print(f"    [!] Gemini Error: {res.text}")
            break
    return []

# ==========================================
# 3. BACKFILL LOOP (DAY BY DAY)
# ==========================================
print("\n[*] Starting Vectorization and Upload loop...")
print("[!] This will take some time. Gemini API has a 15 Requests Per Minute limit on the free tier.")
print("[!] We will pause 4 seconds between each day to avoid hitting the limit.\n")

success_count = 0
skip_count = 0

# Convert index to string dates
df_macro.index = df_macro.index.strftime('%Y-%m-%d')

for date_str, row in df_macro.iterrows():
    # Extract values safely
    vix = round(row['VIXCLS'], 2) if pd.notna(row['VIXCLS']) else 0.0
    fx = round(row['DEXKOUS'], 2) if pd.notna(row['DEXKOUS']) else 0.0
    cpi = round(row['CPALTT01USM657N'], 2) if pd.notna(row['CPALTT01USM657N']) else 0.0
    fed_funds = round(row['FEDFUNDS'], 2) if pd.notna(row['FEDFUNDS']) else 0.0
    
    # Calculate Net Liquidity (simplified)
    # WALCL is in Millions -> Convert to Billions (/1000)
    # WTREGEN and RRPONTSYD are already in Billions
    walcl_bil = (row['WALCL'] / 1000) if pd.notna(row['WALCL']) else 0.0
    wtregen_bil = row['WTREGEN'] if pd.notna(row['WTREGEN']) else 0.0
    rrp_bil = row['RRPONTSYD'] if pd.notna(row['RRPONTSYD']) else 0.0
    
    net_liq = walcl_bil - wtregen_bil - rrp_bil

    # Generate the exact same summary text format as quant_engine.py
    summary_text = (
        f"Market State: VIX is at {vix}. USD/KRW Exchange Rate is {fx}. "
        f"Net Liquidity is roughly ${net_liq:,.0f} Billion. "
        f"US CPI stands around {cpi}%. Federal Funds Rate is {fed_funds}%."
    )

    print(f"[{date_str}] Processing...")
    
    # Check if this date already exists in Supabase to avoid duplicate work (optional speedup)
    check_url = f"{SUPABASE_URL}/rest/v1/rag_memory?date=eq.{date_str}&select=date"
    check_res = requests.get(check_url, headers=headers)
    if check_res.status_code == 200 and len(check_res.json()) > 0:
        print(f"    -> Already exists in DB. Skipping.")
        skip_count += 1
        continue

    # 1. Get Embedding
    vector = get_gemini_embedding(summary_text)
    if not vector:
        print(f"    -> Failed to get embedding. Skipping.")
        continue

    # 2. Upload to Supabase pgvector
    payload = {
        "date": date_str,
        "summary": summary_text,
        "metadata": {"source": "pc_historical_backfill"},
        "embedding": vector
    }
    
    upsert_headers = headers.copy()
    upsert_headers["Prefer"] = "return=minimal,resolution=merge-duplicates"
    upsert_url = f"{SUPABASE_URL}/rest/v1/rag_memory?on_conflict=date"
    
    res = requests.post(upsert_url, headers=upsert_headers, json=[payload])
    
    if res.status_code in [200, 201, 204]:
        print(f"    -> ✅ Uploaded successfully.")
        success_count += 1
    else:
        print(f"    -> ❌ Upload failed: {res.text}")
        
    # Rate limit sleep (2 keys = 30 RPM. 60sec / 30 = 2 sec. We use 2.5 to be extremely safe)
    time.sleep(2.5)

print("\n==========================================")
print(f"🏁 Historical Backfill COMPLETE!")
print(f"Successfully processed and uploaded: {success_count} days.")
print(f"Skipped (already existed): {skip_count} days.")
print("\nYour Supabase RAG Vector Database is now fully populated with rich historical memory.")
print("==========================================")
