from config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY
from supabase import create_client

print("URL:", SUPABASE_URL)
print("KEY length:", len(SUPABASE_KEY) if SUPABASE_KEY else 0)
print("SERVICE KEY length:", len(SUPABASE_SERVICE_KEY) if SUPABASE_SERVICE_KEY else 0)

try:
    print("\n--- Testing with Service Key ---")
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    res = client.table("news_sentiment").select("*").limit(1).execute()
    print("Service Key Success:", res)
except Exception as e:
    print("Service Key Failed:", e)
    
try:
    print("\n--- Testing with Anon Key ---")
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    res = client.table("news_sentiment").select("*").limit(1).execute()
    print("Anon Key Success:", res)
except Exception as e:
    print("Anon Key Failed:", e)
