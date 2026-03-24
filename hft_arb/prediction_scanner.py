import requests
import json
import time

POLYMARKET_GAMMA_URL = "https://gamma-api.polymarket.com/markets"

def fetch_polymarket_data():
    """
    Fetches the top volume markets from Polymarket.
    """
    params = {
        "limit": 10,
        "order": "volume24hr",
        "active": "true",
        "closed": "false"
    }
    try:
        resp = requests.get(POLYMARKET_GAMMA_URL, params=params)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Error fetching Polymarket data: {e}")
    return []

def scan_prediction_gaps():
    print("=== Prediction Market Arb Scanner (Prototype) ===")
    poly_data = fetch_polymarket_data()
    
    if not poly_data:
        print("No Polymarket data found.")
        return

    for market in poly_data:
        question = market.get('question', 'Unknown')
        # Typical Polymarket response has outcomes (e.g., [Yes, No])
        # and respective odds/prices.
        
        # Mock Limitless Price (Usually +/- 2-5% gap)
        # In a real scanner, we would fetch from Limitless GraphQL here.
        poly_price = 0.5  # Default placeholder
        try:
            # Polymarket prices are often in 'tokens' or odds
            # This is a simplified extraction
            poly_price = float(market.get('outcomePrices', [0.5])[0])
        except:
            pass
            
        limitless_price = poly_price * 1.05  # Mock 5% gap
        
        gap_pct = abs(poly_price - limitless_price) * 100
        
        print(f"Event: {question[:50]}...")
        print(f"  Polymarket: ${poly_price:.2f} | Limitless (Mock): ${limitless_price:.2f}")
        print(f"  Detected Gap: {gap_pct:.2f}%")
        
        if gap_pct > 3.0:
            print(f"  >>> [SIGNAL] Arbitrage Opportunity Found! (Gap > 3%)")
        print("-" * 40)

if __name__ == "__main__":
    scan_prediction_gaps()
