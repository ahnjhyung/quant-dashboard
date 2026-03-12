
import os
from notion_client import Client
from config import NOTION_API_KEY, NOTION_PARENT_PAGE_ID, NOTION_DATABASE_ID

def check_notion_db():
    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        print("API Key or Database ID missing")
        return
    
    client = Client(auth=NOTION_API_KEY)
    try:
        print(f"AVAILABLE METHODS: {dir(client.databases)}")
        db_id = "31f9d833-cbff-81b6-86c9-f0035400f7fe"
        
        # 쿼리가 안되면 retrieve의 결과라도 다시 상세히 봅니다.
        db = client.databases.retrieve(database_id=db_id)
        import json
        print(f"FULL DB OBJECT KEYS: {db.keys()}")
        if "properties" in db:
            print("=== Properties Found ===")
            for k, v in db["properties"].items():
                print(f"- {k}: {v['type']}")
        else:
            print("Properties key is MISSING in db object.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_notion_db()
