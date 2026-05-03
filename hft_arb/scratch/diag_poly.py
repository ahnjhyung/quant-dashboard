
import asyncio
import aiohttp
import logging
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.append(str(Path(__file__).parent.parent.parent))

from hft_arb.prediction_scanner import PolymarketScanner

async def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("\n" + "="*50)
    print("--- Polymarket Real-time Diagnostic ---")
    print("="*50)
    
    scanner = PolymarketScanner()
    semaphore = asyncio.Semaphore(10)
    
    async with aiohttp.ClientSession() as session:
        # 1. CLOB 마켓 조회
        print("\n[1/3] Fetching CLOB-active markets...")
        data = await scanner.fetch_clob_markets(session)
        print(f"-> Response Type: {type(data)}")
        
        if isinstance(data, dict):
            print(f"-> Response Keys: {list(data.keys())}")
            # 'data' 또는 유사한 키가 있는지 확인
            markets = data.get("data", data.get("markets", []))
            if not markets and data: # 만약 키 없이 딕셔너리 그 자체가 데이터라면 (드문 경우)
                 markets = [data]
        else:
            markets = data

        print(f"-> Extracted {len(markets) if isinstance(markets, list) else 0} markets.")

        # 3. 샘플 마켓 스캔 테스트
        print(f"\n[2/3] Testing top 5 markets for real-time prices...")
        for m in markets[:5]:
            print(f"\n--- Market: {m.get('question', 'Unknown')[:50]}... ---")
            await scanner.scan_market(session, m, semaphore)
            
    print("\n" + "="*50)
    print("--- Diagnostic Complete ---")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
