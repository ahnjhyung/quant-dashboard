import os
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from dotenv import load_dotenv

def main():
    load_dotenv()
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    
    client = ClobClient(
        host="https://clob.polymarket.com",
        key=private_key,
        chain_id=POLYGON
    )
    
    print("Searching for 2024-2025 ACTIVE markets...")
    market_ids = client.get_sampling_markets()
    
    # market_ids is likely a list of strings
    if not isinstance(market_ids, list):
        print(f"Unexpected type: {type(market_ids)}")
        return

    for mid in market_ids[:20]: # Check first 20
        try:
            m = client.get_market(mid)
            question = m.get("question", "")
            if "2024" in question or "2025" in question or "Bitcoin" in question:
                print(f"Market: {question} | Condition ID: {m.get('condition_id')}")
                tokens = m.get("tokens", [])
                for t in tokens:
                    print(f"  Token: {t.get('outcome')} | ID: {t.get('token_id')}")
                print("-" * 40)
                # Break once we find a good candidate
                break
        except Exception as e:
            continue

if __name__ == "__main__":
    main()
