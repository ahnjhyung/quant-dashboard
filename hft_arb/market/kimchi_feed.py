"""
kimchi_feed.py
==============
업비트와 바이낸스의 실시간 가격을 3개 자산(BTC, ETH, SOL)에 대해 수집하고
김치 프리미엄을 실시간으로 계산하여 브로드캐스팅함.
"""
import time
import requests
from typing import Dict, List, Optional, Any

class KimchiPremiumFeed:
    SYNC_SYMBOLS = ["BTC", "ETH", "SOL"]
    
    def __init__(self):
        self._latest_data: Dict[str, Dict[str, Any]] = {}
        self.fx_rate = 1400.0 # 기본 환율 (실제론 API 연동 필요)

    def fetch_prices(self) -> Dict[str, Dict[str, Any]]:
        """업비트/바이낸스 동시 가격 조회"""
        # 1. 환율 업데이트 (간소화를 위해 1회성 or 고정)
        # 2. 업비트 시세 (KRW-BTC, ETH, SOL)
        try:
            upbit_url = "https://api.upbit.com/v1/ticker"
            up_symbols = [f"KRW-{s}" for s in self.SYNC_SYMBOLS]
            up_res = requests.get(upbit_url, params={"markets": ",".join(up_symbols)}, timeout=2)
            up_data = {item['market']: item['trade_price'] for item in up_res.json()}
            
            # 3. 바이낸스 시세 (BTCUSDT, ETHUSDT, SOLUSDT)
            bin_url = "https://api.binance.com/api/v3/ticker/price"
            prices = {}
            for s in self.SYNC_SYMBOLS:
                b_sym = f"{s}USDT"
                b_res = requests.get(bin_url, params={"symbol": b_sym}, timeout=2)
                b_price = float(b_res.json()['price'])
                
                u_price = up_data.get(f"KRW-{s}", 0.0)
                
                if u_price > 0 and b_price > 0:
                    premium = (u_price / (b_price * self.fx_rate) - 1) * 100
                    prices[s] = {
                        "upbit": u_price,
                        "binance": b_price,
                        "premium": premium,
                        "timestamp": time.time()
                    }
            
            self._latest_data = prices
            return prices
        except Exception as e:
            print(f"[FEED ERROR] {e}")
            return {}

    def get_latest(self) -> Dict[str, Dict[str, Any]]:
        return self._latest_data


if __name__ == "__main__":
    feed = KimchiPremiumFeed()
    print("Starting Live Kimchi Feed (3 Assets)...")
    for _ in range(5):
        data = feed.fetch_prices()
        for s, v in data.items():
            print(f"[{s}] UP: {v['upbit']:>12,.0f} | Bin: {v['binance']:>8.2f} | KP: {v['premium']:>+.2f}%")
        time.sleep(1)
