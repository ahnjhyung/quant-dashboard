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
                'T10Y3M', 'T10Y2Y', 'DGS2', 'DGS10', 'DGS30',                   # Interest Rates / Yield Curve
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
                'TOTDTEUSQ163N', 'TDSP', 'BAMLH0A0HYM2EY', 'GS10',            # Debt / Yields
                'SOFR',                                                         # SOFR 금리 (단기 기준금리)
            ],
            "YFINANCE": [
                'BTC-USD', 'GC=F', 'CL=F', '^GSPC', '^IXIC', 'DX-Y.NYB',
                'HYG', 'LQD', '^KS11', '^KQ11'                                # KOSPI, KOSDAQ
            ]
        }

    def collect_fred_data(self, days: int = 30):
        """FRED 지표 수집 및 적재 (최근 데이터 업데이트)"""
        if not self.fred:
            print("[ERROR] FRED API Key missing.")
            return

        start_date = datetime.now() - timedelta(days=days)

        for ticker in self.indicators["FRED"]:
            try:
                print(f"[*] Collecting FRED: {ticker}...")
                # 최근 'days' 기간의 데이터를 가져옴
                if ticker in ['CPIAUCSL', 'PCEPI']:
                    series = self.fred.get_series(ticker, observation_start=start_date, units='pc1')
                else:
                    series = self.fred.get_series(ticker, observation_start=start_date)
                if series is not None and not series.empty:
                    count = 0
                    for date, value in series.items():
                        if pd.isna(value): continue
                        
                        date_str = date.strftime("%Y-%m-%d")
                        # 이미 존재하는지 체크
                        if not self.db.check_macro_exists(ticker, date_str):
                            self.db.upsert_macro_indicator(ticker, date_str, float(value))
                            count += 1
                    
                    if count > 0:
                        print(f"    [OK] FRED {ticker}: {count} new points saved.")
                    else:
                        print(f"    [SKIP] FRED {ticker}: No new data.")
                
                time.sleep(0.3) # Rate limit 방어
            except Exception as e:
                print(f"    [ERROR] FRED {ticker} 수집 실패: {e}")

    def collect_yfinance_data(self):
        """yfinance 지표 수집 및 적재 (최근 5일치 체크)"""
        for ticker in self.indicators["YFINANCE"]:
            try:
                print(f"[*] Collecting yfinance: {ticker}...")
                data = yf.download(ticker, period="5d", progress=False)
                if not data.empty:
                    count = 0
                    for date, row in data.iterrows():
                        date_str = date.strftime("%Y-%m-%d")
                        val = float(row['Close'].iloc[0]) if hasattr(row['Close'], 'iloc') else float(row['Close'])
                        
                        if not self.db.check_macro_exists(ticker, date_str):
                            self.db.upsert_macro_indicator(ticker, date_str, val)
                            count += 1
                    
                    if count > 0:
                        print(f"    [OK] yf {ticker}: {count} new points saved.")
                    else:
                        print(f"    [SKIP] yf {ticker}: No new data.")
            except Exception as e:
                print(f"    [ERROR] yfinance {ticker} 수집 실패: {e}")

    def calculate_and_save_net_liquidity(self):
        """
        Net Liquidity 산출 및 저장 (업데이트 주기 유지)
        Formula: WALCL - TGA - RRP
        """
        if not self.fred: return
        print("[*] Calculating NET_LIQUIDITY (preserving frequency)...")
        try:
            # 최근 90일 데이터 확보하여 시계열 분석
            start_date = datetime.now() - timedelta(days=90)
            
            walcl = self.fred.get_series('WALCL', observation_start=start_date).dropna()
            tga = self.fred.get_series('WDTGAL', observation_start=start_date).dropna()
            rrp = self.fred.get_series('RRPONTSYD', observation_start=start_date).dropna()
            
            # 주간 지표인 WALCL 기준으로 인덱스 생성
            df = pd.DataFrame({'walcl': walcl, 'tga': tga, 'rrp': rrp})
            # ffill로 다른 지표들의 최신값을 매칭시키되, 인덱스는 원본 날짜 유지
            df = df.ffill().dropna()
            
            count = 0
            for date, row in df.iterrows():
                date_str = date.strftime("%Y-%m-%d")
                
                # 단위 환산 (B)
                val_walcl_b = row['walcl'] / 1000.0
                val_tga_b = row['tga'] / 1000.0
                val_rrp_b = row['rrp'] # RRP는 이미 B 단위인 경우가 많으나 FRED ticker에 따라 다름 (RRPONTSYD는 B)
                
                net_liq = val_walcl_b - val_tga_b - val_rrp_b
                
                # 중복 저장 방지
                if not self.db.check_macro_exists("NET_LIQUIDITY", date_str):
                    self.db.upsert_macro_indicator("NET_LIQUIDITY", date_str, float(net_liq))
                    self.db.upsert_macro_indicator("WALCL_B", date_str, float(val_walcl_b))
                    self.db.upsert_macro_indicator("TGA_B", date_str, float(val_tga_b))
                    self.db.upsert_macro_indicator("RRP_B", date_str, float(val_rrp_b))
                    count += 1
            
            print(f"    [OK] NET_LIQUIDITY: {count} new periods calculated.")
                
        except Exception as e:
            print(f"    [ERROR] NET_LIQUIDITY 계산 실패: {e}")

    def collect_tvdatafeed_data(self):
        """TradingView 실시간 지표 수집 및 적재 (FRED의 지연 보완)"""
        try:
            from tvDatafeed import TvDatafeed, Interval
            tv = TvDatafeed()
            
            # (ticker, exchange, db_ticker)
            tv_tickers = [
                ('US02Y', 'TVC', 'DGS2'),
                ('US10Y', 'TVC', 'DGS10'),
                ('US30Y', 'TVC', 'DGS30'),
                ('VIX', 'CBOE', 'VIXCLS'),
                ('USDKRW', 'FX_IDC', 'DEXKOUS'),
            ]
            
            # 실시간 금리차(T10Y2Y) 계산용 저장소
            latest_yields = {}
            
            for symbol, exchange, db_ticker in tv_tickers:
                print(f"[*] Collecting TradingView: {symbol} ({db_ticker})...")
                # 당일 포함 최근 3일 데이터 가져오기
                df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_daily, n_bars=3)
                if df is not None and not df.empty:
                    count = 0
                    for date, row in df.iterrows():
                        date_str = date.strftime("%Y-%m-%d")
                        val = float(row['close'])
                        
                        # 당일 데이터 갱신을 위해 존재하는지 체크하고, 존재하더라도 오늘 날짜면 덮어쓰기!
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        if not self.db.check_macro_exists(db_ticker, date_str):
                            self.db.upsert_macro_indicator(db_ticker, date_str, val)
                            count += 1
                        elif date_str == today_str:
                            self.db.upsert_macro_indicator(db_ticker, date_str, val)
                            count += 1
                            
                        # 당일 값을 T10Y2Y 계산용으로 저장
                        if date_str == today_str:
                            latest_yields[db_ticker] = val
                            
                    if count > 0:
                        print(f"    [OK] TradingView {symbol}: {count} points updated.")
                    else:
                        print(f"    [SKIP] TradingView {symbol}: No new updates.")
                time.sleep(0.5)
                
            # 실시간 T10Y2Y 업데이트
            if 'DGS10' in latest_yields and 'DGS2' in latest_yields:
                spread = latest_yields['DGS10'] - latest_yields['DGS2']
                today_str = datetime.now().strftime("%Y-%m-%d")
                self.db.upsert_macro_indicator('T10Y2Y', today_str, spread)
                print(f"    [OK] TradingView T10Y2Y Spread Updated: {spread:.3f}")
                
        except ImportError:
            print("[ERROR] tvDatafeed module not installed. Run: pip install git+https://github.com/rongardF/tvdatafeed.git")
        except Exception as e:
            print(f"[ERROR] TradingView collection failed: {e}")

    def run_all(self):
        print(f"=== [Unified] 매크로 데이터 통합 수집 시작 ({datetime.now()}) ===")
        self.collect_fred_data()
        self.collect_yfinance_data()
        self.calculate_and_save_net_liquidity()
        self.collect_tvdatafeed_data()
        print("=== 매크로 데이터 통합 수집 완료 ===")

if __name__ == "__main__":
    collector = MacroDataCollector()
    collector.run_all()
