"""
Macro Data Collector (Unified with GAS)
=======================================
- FRED 및 yfinance 데이터를 수집하여 Supabase `macro_indicators` 테이블에 적재.
- 기존 Google Apps Script(GAS) 수집기와 지표 리스트를 동기화하고, 중복 수집 방지 로직(Exists Check)을 포함합니다.
"""

import time
import pandas as pd
import yfinance as yf
from fredapi import Fred
from datetime import datetime, timedelta
from config import FRED_API_KEY
from data_collectors.supabase_manager import SupabaseManager

class MacroDataCollector:
    def __init__(self):
        self.fred = Fred(api_key=FRED_API_KEY) if FRED_API_KEY else None
        self.db = SupabaseManager()
        
        # GAS(Google Apps Script) 수집기와 동기화된 지표 리스트
        self.indicators = {
            "FRED": [
                # 1. Leading Indicators (선행지표)
                'T10Y3M', 'T10Y2Y', 'DGS2', 'DGS10',                          # Interest Rates / Yield Curve
                'PERMIT', 'AWHAETP', 'UMCSENT', 'AMTMNO', 'DGORDER',          # Real Economy / Sentiment
                'ICSA', 'NAPM', 'CSCICP03USM665S',                            # Jobless Claims / ISM PMI / OECD CCI
                'NEWORDER', 'BUSLOANS',                                       # Demand / Credit
                
                # 2. Coincident Indicators (동행지표)
                'PAYEMS', 'UNRATE', 'INDPRO', 'IPMAN', 'DEXKOUS',             # Jobs / Production / FX
                'M2SL', 'M2V', 'WALCL', 'WDTGAL', 'RRPONTSYD',                # Liquidity / Central Bank
                'DTWEXBGS', 'GDP', 'AWHMAN',                                  # Economy Scale
                'KRGDPNQDSMEI',                                               # Korea GDP
                
                # 3. Lagging / Stress Indicators (후행/스트레스지표)
                'CPIAUCSL', 'PCEPI', 'T5YIE', 'REAINTRATREARAT10Y',           # Inflation / Real Rates
                'NFCI', 'TEDRATE', 'BAMLH0A0HYM2', 'VIXCLS',                  # Stress / Risk
                'TOTDTEUSQ163N', 'TDSP', 'BAMLH0A0HYM2EY', 'GS10'             # Debt / Yields
            ],
            "YFINANCE": [
                'BTC-USD', 'GC=F', 'CL=F', '^GSPC', '^IXIC', 'DX-Y.NYB',
                'HYG', 'LQD', '^KS11', '^KQ11'                                # KOSPI, KOSDAQ
            ]
        }

    def collect_fred_data(self):
        """FRED 지표 수집 및 적재 (DB 체크 포함)"""
        if not self.fred:
            print("[ERROR] FRED API Key missing.")
            return

        today_str = datetime.now().strftime("%Y-%m-%d")

        for ticker in self.indicators["FRED"]:
            try:
                # 1. 중복 체크 (GAS가 이미 수집했거나, 오늘 이미 수집했다면 Skip)
                if self.db.check_macro_exists(ticker, today_str):
                    print(f"    [SKIP] FRED {ticker}: Already exists for {today_str}")
                    continue

                print(f"[*] Collecting FRED: {ticker}...")
                # 최신 1개 관측치만 가져옴 (FRED API 호출 최소화)
                series = self.fred.get_series(ticker, limit=1)
                if series is not None and not series.empty:
                    date = series.index[-1]
                    value = series.iloc[-1]
                    date_str = date.strftime("%Y-%m-%d")
                    
                    if not pd.isna(value):
                        self.db.upsert_macro_indicator(ticker, date_str, float(value))
                        print(f"    [OK] FRED {ticker} ({date_str}): {value}")
                
                time.sleep(0.3) # Rate limit 방어
            except Exception as e:
                print(f"    [ERROR] FRED {ticker} 수집 실패: {e}")

    def collect_yfinance_data(self):
        """yfinance 지표 수집 및 적재 (DB 체크 포함)"""
        today_str = datetime.now().strftime("%Y-%m-%d")

        for ticker in self.indicators["YFINANCE"]:
            try:
                if self.db.check_macro_exists(ticker, today_str):
                    print(f"    [SKIP] yfinance {ticker}: Already exists for {today_str}")
                    continue

                print(f"[*] Collecting yfinance: {ticker}...")
                data = yf.download(ticker, period="1d", progress=False)
                if not data.empty:
                    last_row = data.iloc[-1]
                    date_str = data.index[-1].strftime("%Y-%m-%d")
                    val = float(last_row['Close'].iloc[0]) if hasattr(last_row['Close'], 'iloc') else float(last_row['Close'])
                    
                    self.db.upsert_macro_indicator(ticker, date_str, val)
                    print(f"    [OK] yf {ticker} ({date_str}): {val}")
            except Exception as e:
                print(f"    [ERROR] yfinance {ticker} 수집 실패: {e}")



    def calculate_and_save_net_liquidity(self):
        """
        Net Liquidity 산출 및 저장
        Formula: Fed Total Assets (WALCL) - TGA (WDTGAL) - Reverse Repo (RRPONTSYD)
        Units: FRED data is in Millions (WALCL, WDTGAL) and Billions (RRP). 
        Result will be stored in Billions (B) for easier UI display.
        """
        if not self.fred: return
        print("[*] Calculating NET_LIQUIDITY (Billions USD)...")
        try:
            # 최근 30일 데이터 확보하여 날짜 매칭
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            walcl = self.fred.get_series('WALCL', observation_start=start_date).dropna()
            tga = self.fred.get_series('WDTGAL', observation_start=start_date).dropna()
            rrp = self.fred.get_series('RRPONTSYD', observation_start=start_date).dropna()
            
            # 데이터프레임으로 통합하여 날짜 맞춤
            df = pd.DataFrame({'walcl': walcl, 'tga': tga, 'rrp': rrp})
            df = df.fillna(method='ffill').dropna() # 이전 값으로 채우기 (발표 주기가 다름)
            
            if not df.empty:
                latest = df.iloc[-1]
                # WALCL(M), TGA(M), RRP(B) -> 모두 B(Billions)로 통일
                # Net Liq (B) = (WALCL / 1000) - (TGA / 1000) - RRP
                val_walcl_b = latest['walcl'] / 1000.0
                val_tga_b = latest['tga'] / 1000.0
                val_rrp_b = latest['rrp']
                
                net_liquidity_b = val_walcl_b - val_tga_b - val_rrp_b
                date_str = df.index[-1].strftime("%Y-%m-%d")
                
                self.db.upsert_macro_indicator("NET_LIQUIDITY", date_str, float(net_liquidity_b))
                print(f"    [OK] NET_LIQUIDITY ({date_str}): {net_liquidity_b:,.2f}B USD")
                
                # 원본 지표들도 B 단위로 저장 (UI 일관성)
                self.db.upsert_macro_indicator("WALCL_B", date_str, float(val_walcl_b))
                self.db.upsert_macro_indicator("TGA_B", date_str, float(val_tga_b))
                self.db.upsert_macro_indicator("RRP_B", date_str, float(val_rrp_b))
        except Exception as e:
            print(f"    [ERROR] NET_LIQUIDITY 산출 실패: {e}")

    def run_all(self):
        print(f"=== [Unified] 매크로 데이터 통합 수집 시작 ({datetime.now()}) ===")
        self.collect_fred_data()
        self.collect_yfinance_data()
        self.calculate_and_save_net_liquidity()
        print("=== 매크로 데이터 통합 수집 완료 ===")

if __name__ == "__main__":
    collector = MacroDataCollector()
    collector.run_all()
