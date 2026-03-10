import os
import json
import requests
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyAxQvT3UDLp0J9ocxhmeWENi0-YRhP50XQ")
GEMINI_REST_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={GEMINI_API_KEY}"

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://fcuenflxkkpyplehsizg.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZjdWVuZmx4a2tweXBsZWhzaXpnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2OTUxNTk2OCwiZXhwIjoyMDg1MDkxOTY4fQ.Ic-Hc8j67bkYsUKTmcbwh5RwjI84PNS6W75lkW_bnEs")

class VectorMemory:
    def __init__(self):
        print("--- [VectorStore] Initializing Supabase pgvector Connection ---")
        self.sb_headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    def _get_embedding(self, text: str) -> list:
        """Helper to get embeddings from Google Gemini using raw REST APIs (No gRPC/SDK)."""
        try:
            headers = {"Content-Type": "application/json"}
            payload = {
                "content": {
                    "parts": [{"text": text}]
                },
                "taskType": "RETRIEVAL_DOCUMENT"
            }
            response = requests.post(GEMINI_REST_URL, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()
            return data.get('embedding', {}).get('values', [])
        except Exception as e:
            print(f"[ERROR] Gemini REST API Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return []

    def save_daily_memory(self, date_str: str, market_summary_text: str, metadata: dict = None):
        """
        Saves today's market conditions (summary text) into Supabase pgvector.
        """
        if not metadata:
            metadata = {}
        
        metadata['date'] = date_str

        # Generate Embedding using Gemini
        embedding = self._get_embedding(market_summary_text)
        
        if embedding:
            payload = {
                "date": date_str,
                "summary": market_summary_text,
                "embedding": f"[{','.join(map(str, embedding))}]", # pgvector format: '[0.1, 0.2, ...]'
                "metadata": metadata
            }
            
            upsert_headers = self.sb_headers.copy()
            upsert_headers["Prefer"] = "return=representation,resolution=merge-duplicates"
            
            try:
                url_upsert = f"{SUPABASE_URL}/rest/v1/rag_memory?on_conflict=date"
                res = requests.post(url_upsert, headers=upsert_headers, json=[payload])
                res.raise_for_status()
                print(f"--- [OK] Memorized market condition for {date_str} in Supabase pgvector ---")
            except Exception as e:
                print(f"[ERROR] Failed to save memory to Supabase: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"Response: {e.response.text}")

    def recall_similar_situations(self, current_summary_text: str, k: int = 3) -> list:
        """
        Queries Supabase pgvector via RPC for 'k' past days most similar to today's summary.
        """
        print(f"--- [INFO] Searching Supabase pgvector for {k} similar historical situations... ---")
        
        query_embedding = self._get_embedding(current_summary_text)
        if not query_embedding:
            return []

        try:
            payload = {
                "query_embedding": f"[{','.join(map(str, query_embedding))}]",
                "match_threshold": 0.0, # Adjust if needed (0 to 1)
                "match_count": k + 1 # +1 in case we match the exact same day
            }
            url_rpc = f"{SUPABASE_URL}/rest/v1/rpc/match_rag_memory"
            res = requests.post(url_rpc, headers=self.sb_headers, json=payload)
            res.raise_for_status()
            
            data = res.json()
            results = []
            
            for row in data:
                # We do not compare a date to itself if it was just saved before query
                if row.get('summary') == current_summary_text:
                    continue
                
                # Our SQL returns similarity. We want the top K.
                # In previous code, distance was 1 - similarity. Let's keep that API compatible.
                similarity = row.get('similarity', 0.0)
                distance = 1.0 - similarity
                
                results.append({
                    "date": row.get('date', 'Unknown'),
                    "summary": row.get('summary', ''),
                    "similarity": similarity,
                    "distance": round(distance, 4)
                })

            # The RPC already sorted them, but just slice to k
            return results[:k]
            
        except Exception as e:
            print(f"[ERROR] Failed to recall scenarios from Supabase: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return []

if __name__ == "__main__":
    test_db = VectorMemory()
    
    # Simulate saving past days
    test_db.save_daily_memory(
        "2023-10-15",
        "VIX is jumping. Fed hinted at prolonged high rates. Dollar strength continues. SPY dropped.",
        {"vix_trend": "up", "rates": "high"}
    )
    
    test_db.save_daily_memory(
        "2024-01-10",
        "CPI came in lower than expected. Equities are rallying, Gold is breaking out.",
        {"cpi_trend": "down", "market_mode": "bull"}
    )

    # Simulate querying today
    today_context = "Inflation data is soft, market expects rate cuts. Tech stocks and gold are surging."
    recalled = test_db.recall_similar_situations(today_context, k=1)
    
    print("\n--- Recall Result ---")
    print(json.dumps(recalled, indent=2, ensure_ascii=False))