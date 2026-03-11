from config import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client
from datetime import datetime

client = create_client(SUPABASE_URL, SUPABASE_KEY)
test_data = [{
    "symbol": "TEST_INSERT",
    "title": "Test Title",
    "content": "Test Content",
    "sentiment_score": 50,
    "buzz_volume": 1,
    "date": datetime.utcnow().strftime('%Y-%m-%d')
}]

try:
    print("Attempting to insert using Anon Key...")
    res = client.table("news_sentiment").insert(test_data).execute()
    print("Insert Success:", res)
except Exception as e:
    print("Insert Failed:", e)
