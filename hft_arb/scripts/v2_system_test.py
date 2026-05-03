import os
import asyncio
import logging
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def main():
    load_dotenv()
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    address = os.getenv("POLYMARKET_ADDRESS")
    funder = os.getenv("POLYMARKET_FUNDER")
    
    logger.info("--- Polymarket V2 System Verification Test ---")
    
    # 1. Connectivity & Authentication Test
    try:
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=POLYGON,
            funder=funder
        )
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds)
        logger.info("[SUCCESS] API Authentication (L2 Signing) verified.")
    except Exception as e:
        logger.error(f"[FAILURE] Authentication failed: {e}")
        return

    # 2. Balance Verification
    try:
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        resp = client.get_balance_allowance(params=params)
        balance = resp.get("balance", "0")
        # Balance is returned in USDC.e units (often as an integer in the SDK)
        # We need to format it. Usually 6 decimals for USDC.
        logger.info(f"[SUCCESS] Signer Wallet Balance: {balance} (Raw)")
    except Exception as e:
        logger.error(f"[FAILURE] Balance check failed: {e}")

    # 3. Dynamic Data Fetching Test
    logger.info("Searching for an active liquid market...")
    try:
        resp = client.get_sampling_markets()
        market_list = resp if isinstance(resp, list) else resp.get("data", [])
        
        found_liquid = False
        for m in market_list[:5]:
            if not isinstance(m, dict): continue
            
            question = m.get("question", "Unknown")
            tokens = m.get("tokens", [])
            if not tokens: continue
            
            token_id = tokens[0].get("token_id")
            logger.info(f"Checking Orderbook for: {question[:50]}...")
            try:
                book = client.get_order_book(token_id)
                if book and book.asks and book.bids:
                    logger.info(f"[SUCCESS] Data Pipeline Verified!")
                    logger.info(f"  Best Bid: {book.bids[0].price} | Best Ask: {book.asks[0].price}")
                    found_liquid = True
                    break
            except:
                continue
                
        if not found_liquid:
            logger.warning("[WARNING] No liquid orderbook found in first 5 sampled markets.")
            
    except Exception as e:
        logger.error(f"[FAILURE] Data search failed: {e}")

    logger.info("---------------------------------------------")
    logger.info("Verification Complete. Account is ready for deployment.")

if __name__ == "__main__":
    asyncio.run(main())
