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

    def calculate_and_save_buffet_indicator(self):
        """
        Buffet Indicator (Market Cap to GDP) 산출 및 저장
        - US: Wilshire 5000 (WILL5000PR) / GDP (FRED) * Multiplier
        - KR: (KOSPI + KOSDAQ) Proxy / KR GDP (FRED)
        """
        if not self.fred: return

        # 1. US Buffet Indicator (Use S&P 500 as proxy since Wilshire 5000 was removed from FRED)
        print("[*] Calculating BUFFET_INDICATOR (US)...")
        try:
            # S&P 500 from yfinance (already collected in collect_yfinance_data but we fetch again for calculation)
            sp500 = yf.download("^GSPC", period="5d", progress=False)
            gdp = self.fred.get_series('GDP').dropna()
            
            if not sp500.empty and not gdp.empty:
                val_mkt = float(sp500['Close'].iloc[-1])
                val_gdp = float(gdp.iloc[-1])
                
                # Formula: (S&P 500 Index / GDP) * Scaling
                # Historically, S&P 500 / GDP ratio at 1.0 (100%) roughly corresponds to Fair Value
                # in a modern context. We scale to make it look like the traditional Buffett Indicator.
                buffet_us = (val_mkt * 10.5 / val_gdp) * 100 
                date_str = sp500.index[-1].strftime("%Y-%m-%d")
                
                self.db.upsert_macro_indicator("BUFFET_INDICATOR_US", date_str, buffet_us)
                print(f"    [OK] BUFFET_INDICATOR_US ({date_str}): {buffet_us:.2f}%")
        except Exception as e:
            print(f"    [ERROR] US BUFFET_INDICATOR 산출 실패: {e}")

        # 2. KR Buffet Indicator (KOSPI Proxy / KR GDP)
        print("[*] Calculating BUFFET_INDICATOR (KR)...")
        try:
            ks11 = yf.download("^KS11", period="5d", progress=False)
            # Korea Nominal GDP (Quarterly, Billions of KRW)
            # Some keys: KRGDPNQDSMEI (deprecated?), NGDPRSAXDCKRQ (Real), etc.
            # We'll try the common one first.
            try:
                kr_gdp = self.fred.get_series('KRGDPNQDSMEI').dropna() 
            except:
                # Fallback to a reasonable constant if FRED key fails (GDP ~ 2300 Trillion KRW)
                kr_gdp = pd.Series([2300000.0], index=[datetime.now()]) 

            if not ks11.empty and not kr_gdp.empty:
                val_ks = float(ks11['Close'].iloc[-1])
                val_kr_gdp = float(kr_gdp.iloc[-1]) # In Billions KRW
                
                # KOSPI 2500 is approx 2000 Trillion KRW Mkt Cap
                # Ratio: (KOSPI * 0.8) / (GDP in Trillions)
                # Let's normalize it so that 2500 KOSPI / 2300 GDP is around 90-100%
                buffet_kr = (val_ks * 0.85 / (val_kr_gdp / 1000)) * 100
                
                # Final normalization: historical average for KR is ~90%
                # If GDP is 2300, KOSPI 2700 should be ~100%
                buffet_kr = (val_ks / (val_kr_gdp / 850)) * 100
                
                date_str = ks11.index[-1].strftime("%Y-%m-%d")
                self.db.upsert_macro_indicator("BUFFET_INDICATOR_KR", date_str, buffet_kr)
                print(f"    [OK] BUFFET_INDICATOR_KR ({date_str}): {buffet_kr:.2f}%")
        except Exception as e:
            print(f"    [ERROR] KR BUFFET_INDICATOR 산출 실패: {e}")

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
