import os
import requests
from config import NOTION_API_KEY, NOTION_DATABASE_ID

def get_db_info():
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    db_id = NOTION_DATABASE_ID.replace("-", "")
    url = f"https://api.notion.com/v1/databases/{db_id}"
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        print("Database Properties:")
        for prop_name, prop_data in data.get("properties", {}).items():
            print(f"- {prop_name}: {prop_data['type']}")
    else:
        print(f"Error {response.status_code}: {response.text}")

if __name__ == "__main__":
    get_db_info()
