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
                
                # 3. Lagging / Stress Indicators (후행/스트레스지표)
                'CPIAUCSL', 'PCEPI', 'T5YIE', 'REAINTRATREARAT10Y',           # Inflation / Real Rates
                'NFCI', 'TEDRATE', 'BAMLH0A0HYM2', 'VIXCLS',                  # Stress / Risk
                'TOTDTEUSQ163N', 'TDSP', 'BAMLH0A0HYM2EY', 'GS10'             # Debt / Yields
            ],
            "YFINANCE": [
                'BTC-USD', 'GC=F', 'CL=F', '^GSPC', '^IXIC', 'DX-Y.NYB',
                'HYG', 'LQD'
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

    def calculate_and_save_buffet_indicator(self):
        """
        Buffet Indicator (Market Cap to GDP) 산출 및 저장
        Formula: ^GSPC (S&P 500 Index) * Multiplier / GDP (FRED) * 100
        """
        print("[*] Calculating BUFFET_INDICATOR (S&P 500 Proxy)...")
        try:
            # yfinance에서 S&P 500 가져오기
            gspc = yf.download("^GSPC", period="5d", progress=False)
            if not self.fred: return
            
            # GDP의 최신 유효 데이터 가져오기 (분기별 데이터이므로 dropna 필수)
            gdp_series = self.fred.get_series('GDP')
            gdp_series = gdp_series.dropna()
            
            if not gspc.empty and not gdp_series.empty:
                val_mkt = float(gspc['Close'].iloc[-1])
                val_gdp = float(gdp_series.iloc[-1])
                
                if val_gdp > 0:
                    buffet_val = (val_mkt / val_gdp) * 100
                    date_str = gspc.index[-1].strftime("%Y-%m-%d")
                    
                    self.db.upsert_macro_indicator("BUFFET_INDICATOR", date_str, buffet_val)
                    print(f"    [OK] BUFFET_INDICATOR_PROXY ({date_str}): {buffet_val:.2f}%")
        except Exception as e:
            print(f"    [ERROR] BUFFET_INDICATOR 산출 실패: {e}")

    def calculate_and_save_net_liquidity(self):
        """
        Net Liquidity 산출 및 저장
        Formula: Fed Total Assets (WALCL) - TGA (WDTGAL) - Reverse Repo (RRPONTSYD)
        """
        if not self.fred: return
        print("[*] Calculating NET_LIQUIDITY...")
        try:
            # 최신 유효 관측치 확보
            walcl = self.fred.get_series('WALCL').dropna()
            tga = self.fred.get_series('WDTGAL').dropna()
            rrp = self.fred.get_series('RRPONTSYD').dropna()
            
            if not walcl.empty and not tga.empty and not rrp.empty:
                val_walcl = float(walcl.iloc[-1])
                val_tga = float(tga.iloc[-1])
                val_rrp = float(rrp.iloc[-1]) * 1000.0
                
                net_liquidity = val_walcl - val_tga - val_rrp
                date_str = walcl.index[-1].strftime("%Y-%m-%d")
                
                self.db.upsert_macro_indicator("NET_LIQUIDITY", date_str, net_liquidity)
                print(f"    [OK] NET_LIQUIDITY ({date_str}): {net_liquidity:,.0f}M USD")
        except Exception as e:
            print(f"    [ERROR] NET_LIQUIDITY 산출 실패: {e}")

    def run_all(self):
        print(f"=== [Unified] 매크로 데이터 통합 수집 시작 ({datetime.now()}) ===")
        self.collect_fred_data()
        self.collect_yfinance_data()
        self.calculate_and_save_net_liquidity()
        self.calculate_and_save_buffet_indicator()
        print("=== 매크로 데이터 통합 수집 완료 ===")

if __name__ == "__main__":
    collector = MacroDataCollector()
    collector.run_all()
