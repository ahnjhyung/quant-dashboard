import urllib.request
import json
import time
import os
from datetime import datetime

# ============================================================
# KIMCHI SNIPER ULTRA-LIGHT (Version 1.0)
# ============================================================
# - NO pip install required (Standard Library Only)
# - Targeted for Android Termux / Low-power devices
# ============================================================

SYMBOLS = ["BTC", "ETH", "SOL"]
UPBIT_MARKETS = ",".join([f"KRW-{s}" for s in SYMBOLS]) + ",KRW-USDT"

def fetch_json(url):
    """표준 urllib를 이용한 간단한 JSON 페치 함수"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        return None

def get_data():
    # 1. Upbit 데이터 (한 번에 여러 마켓 조회)
    upbit_url = f"https://api.upbit.com/v1/ticker?markets={UPBIT_MARKETS}"
    upbit_res = fetch_json(upbit_url)
    
    # 2. Binance 데이터 (개별 조회)
    binance_data = {}
    for s in SYMBOLS:
        b_url = f"https://api.binance.com/api/v3/ticker/price?symbol={s}USDT"
        b_res = fetch_json(b_url)
        if b_res:
            binance_data[s] = float(b_res['price'])
            
    if not upbit_res or not binance_data:
        return None, None, None
        
    # 환율 추출 (KRW-USDT)
    fx_rate = 1400.0 # fallback
    upbit_prices = {}
    for item in upbit_res:
        m = item['market']
        if m == 'KRW-USDT':
            fx_rate = float(item['trade_price'])
        else:
            sym = m.split('-')[1]
            upbit_prices[sym] = float(item['trade_price'])
            
    return upbit_prices, binance_data, fx_rate

def main():
    os.system('clear' if os.name != 'nt' else 'cls')
    print("=" * 60)
    print("   KIMCHI SNIPER ULTRA-LIGHT - Monitoring Started")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print(f"{'SYMBOL':<8} | {'UPBIT(KRW)':<12} | {'BINANCE($)':<10} | {'PREMIUM':<8}")
    print("-" * 60)

    try:
        while True:
            u_prices, b_prices, fx = get_data()
            
            if u_prices and b_prices and fx:
                # 출력 위치 고정 (터미널 제어 문자로 덮어쓰기 시도 - 일부 지원안될수있음)
                # 여기서는 그냥 한 줄씩 출력
                ts = datetime.now().strftime('%H:%M:%S')
                
                for s in SYMBOLS:
                    u_p = u_prices.get(s, 0)
                    b_p = b_prices.get(s, 0)
                    
                    if u_p > 0 and b_p > 0:
                        # 김프 계산: ((업비트가 / 환율) - 바이낸스가) / 바이낸스가 * 100
                        k_premium = ((u_p / fx) - b_p) / b_p * 100
                        
                        print(f"{s:<8} | {int(u_p):>10,}원 | ${b_p:>9.2f} | {k_premium:>6.2f}%")
                
                print(f"--- [FX: {fx:,.2f}] --- {ts} ---", end='\r')
            
            time.sleep(2) # 2초 간격
    except KeyboardInterrupt:
        print("\nMonitoring Stopped.")

if __name__ == "__main__":
    main()
