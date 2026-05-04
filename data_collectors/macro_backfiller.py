"""
Macro Data Backfiller
======================
- FRED 및 yfinance에서 대량의 과거 데이터를 수집하여 Supabase에 적재.
- On-demand로 호출되어 분석에 필요한 과거 데이터 공백을 메웁니다.
"""

import time
import pandas as pd
from datetime import datetime
from data_collectors.supabase_manager import SupabaseManager
from data_collectors.macro_data_collector import MacroDataCollector
from data_collectors.yf_utils import download_ticker_data

class MacroBackfiller(MacroDataCollector):
    def __init__(self):
        super().__init__()

    def backfill_fred_ticker(self, ticker: str, start_date: str = "1970-01-01"):
        """특정 FRED 티커의 모든 과거 데이터를 수집하여 저장"""
        if not self.fred:
            return
        
        print(f"[*] Backfilling FRED: {ticker} from {start_date}...")
        try:
            series = self.fred.get_series(ticker, observation_start=start_date)
            if series is not None and not series.empty:
                data_list = []
                for date, value in series.items():
                    if pd.isna(value): continue
                    data_list.append({
                        "ticker": ticker,
                        "date": date.strftime("%Y-%m-%d"),
                        "value": float(value),
                        "created_at": datetime.utcnow().isoformat()
                    })
                
                # 벌크 업로드 시도 (Supabase SDK 버전에 따라 upsert 지원 여부 다를 수 있음)
                if data_list:
                    chunk_size = 500
                    for i in range(0, len(data_list), chunk_size):
                        chunk = data_list[i:i + chunk_size]
                        try:
                            # 1. 벌크 시도
                            self.db.client.table("macro_indicators").upsert(chunk, on_conflict="ticker,date").execute()
                        except Exception as inner_e:
                            print(f"    [WARN] Bulk upsert failed, falling back to sequential: {inner_e}")
                            # 2. 개별 시도 (Fallback)
                            for row in chunk:
                                self.db.upsert_macro_indicator(row['ticker'], row['date'], row['value'])
                    print(f"    [OK] {ticker}: {len(data_list)} rows processed.")
            
            time.sleep(0.5) # Rate limit
        except Exception as e:
            print(f"    [ERROR] {ticker} backfill failed: {e}")

    def backfill_yf_ticker(self, ticker: str, start_date: str = "1970-01-01"):
        """특정 yfinance 티커의 모든 과거 데이터를 수집하여 저장"""
        print(f"[*] Backfilling yfinance: {ticker} from {start_date}...")
        try:
            data = download_ticker_data(ticker, start=start_date)
            if not data.empty:
                data_list = []
                for date, row in data.iterrows():
                    val = float(row['Close'].iloc[0]) if hasattr(row['Close'], 'iloc') else float(row['Close'])
                    data_list.append({
                        "ticker": ticker,
                        "date": date.strftime("%Y-%m-%d"),
                        "value": val,
                        "created_at": datetime.utcnow().isoformat()
                    })
                
                if data_list:
                    chunk_size = 1000
                    for i in range(0, len(data_list), chunk_size):
                        chunk = data_list[i:i + chunk_size]
                        self.db.client.table("macro_indicators").upsert(chunk, on_conflict="ticker,date").execute()
                    print(f"    [OK] {ticker}: {len(data_list)} rows inserted.")
        except Exception as e:
            print(f"    [ERROR] {ticker} yfinance backfill failed: {e}")

    def backfill_all_indicators(self, start_date="2004-01-01"):
        """모든 지표에 대해 과거 데이터 수집 (약 5~10분 소요 가능)"""
        print(f"=== [FULL BACKFILL START] Targets: {len(self.indicators['FRED']) + len(self.indicators['YFINANCE'])} tickers ===")
        
        # 1. FRED 지표
        for ticker in self.indicators['FRED']:
            self.backfill_fred_ticker(ticker, start_date=start_date)
            time.sleep(0.5) # API Rate limit
            
        # 2. yfinance 지표
        for ticker in self.indicators['YFINANCE']:
            self.backfill_yf_ticker(ticker, start_date=start_date)
            time.sleep(0.5)

        print("=== [FULL BACKFILL COMPLETE] ===")

    def backfill_net_liquidity(self, start_date: str = "2004-01-01"):
        """순유동성 과거 데이터 계산 및 저장
        
        Formula: WALCL(Fed 자산) - WDTGAL(재무부 잔고) - RRPONTSYD(역RP) * 1000
        WALCL은 주간, WDTGAL/RRPONTSYD는 일간이므로 WALCL 기준으로 리샘플링.
        """
        if not self.fred:
            return
        print(f"[*] Backfilling NET_LIQUIDITY from {start_date}...")
        try:
            walcl = self.fred.get_series('WALCL', observation_start=start_date).dropna()
            tga = self.fred.get_series('WDTGAL', observation_start=start_date).dropna()
            rrp = self.fred.get_series('RRPONTSYD', observation_start=start_date).dropna()

            if walcl.empty or tga.empty:
                print("    [WARN] 구성 지표 데이터 부족")
                return

            # WALCL 날짜 기준으로 TGA/RRP를 forward-fill merge
            df = pd.DataFrame({'walcl': walcl})
            df['tga'] = tga.reindex(df.index, method='ffill')
            df['rrp'] = rrp.reindex(df.index, method='ffill').fillna(0)
            df['net_liq'] = df['walcl'] - df['tga'] - df['rrp'] * 1000.0
            df = df.dropna(subset=['net_liq'])

            data_list = []
            for date, row in df.iterrows():
                data_list.append({
                    "ticker": "NET_LIQUIDITY",
                    "date": date.strftime("%Y-%m-%d"),
                    "value": float(row['net_liq']),
                    "created_at": datetime.utcnow().isoformat()
                })

            if data_list:
                chunk_size = 500
                for i in range(0, len(data_list), chunk_size):
                    chunk = data_list[i:i + chunk_size]
                    self.db.client.table("macro_indicators").upsert(chunk, on_conflict="ticker,date").execute()
                print(f"    [OK] NET_LIQUIDITY: {len(data_list)} rows processed.")
        except Exception as e:
            print(f"    [ERROR] NET_LIQUIDITY backfill failed: {e}")

    def backfill_buffett_indicator(self, start_date: str = "2004-01-01"):
        """버핏 지수 과거 데이터 계산 및 저장
        
        US Formula: WILL5000PR / GDP * 1.15
        KR Formula: (KOSPI / 2500) * 100
        GDP는 분기별이므로 forward-fill 사용.
        """
        if not self.fred:
            return
        
        # 1. US Backfill (Use S&P 500 proxy for consistency)
        print(f"[*] Backfilling BUFFET_INDICATOR_US from {start_date}...")
        try:
            sp500 = download_ticker_data('^GSPC', start=start_date)
            gdp = self.fred.get_series('GDP', observation_start=start_date).dropna()

            if not sp500.empty and not gdp.empty:
                # Helper to get Close price safely
                def get_close(df):
                    if isinstance(df.columns, pd.MultiIndex):
                        return df['Close'].iloc[:, 0]
                    return df['Close']

                sp_close = get_close(sp500)
                df = pd.DataFrame({'sp500': sp_close})
                df['gdp'] = gdp.reindex(df.index, method='ffill')
                df = df.dropna()
                # US Formula: (S&P 500 * 10.5 / GDP) * 100
                df['buffett'] = (df['sp500'] * 10.5 / df['gdp']) * 100
                df_weekly = df.resample('W-FRI').last().dropna()

                data_list = []
                for date, row in df_weekly.iterrows():
                    data_list.append({
                        "ticker": "BUFFET_INDICATOR_US",
                        "date": date.strftime("%Y-%m-%d"),
                        "value": float(row['buffett']),
                        "created_at": datetime.utcnow().isoformat()
                    })

                if data_list:
                    chunk_size = 500
                    for i in range(0, len(data_list), chunk_size):
                        chunk = data_list[i:i + chunk_size]
                        self.db.client.table("macro_indicators").upsert(chunk, on_conflict="ticker,date").execute()
                    print(f"    [OK] BUFFET_INDICATOR_US: {len(data_list)} rows processed.")
        except Exception as e:
            print(f"    [ERROR] BUFFET_INDICATOR_US backfill failed: {e}")

        # 2. KR Backfill (Combined KOSPI + KOSDAQ)
        print(f"[*] Backfilling BUFFET_INDICATOR_KR from {start_date}...")
        try:
            ks11 = download_ticker_data('^KS11', start=start_date)
            kq11 = download_ticker_data('^KQ11', start=start_date)
            
            try:
                # Key: NGDPSAXDCKRQ (Nominal GDP, Millions KRW, Quarterly)
                kr_gdp = self.fred.get_series('NGDPSAXDCKRQ', observation_start=start_date).dropna()
            except:
                kr_gdp = pd.Series([600000000.0], index=[datetime.now()])

            if not ks11.empty and not kq11.empty:
                # Helper to get Close price safely
                def get_close(df):
                    if isinstance(df.columns, pd.MultiIndex):
                        return df['Close'].iloc[:, 0]
                    return df['Close']

                ks_close = get_close(ks11)
                kq_close = get_close(kq11)
                
                df = pd.DataFrame({'ks': ks_close, 'kq': kq_close})
                df['gdp_q'] = kr_gdp.reindex(df.index, method='ffill')
                df = df.dropna(subset=['ks', 'kq', 'gdp_q'])
                
                # Proxy for Market Cap (Trillion KRW)
                # KOSPI factor: ~0.78, KOSDAQ factor: ~0.47
                df['mkt_cap'] = (df['ks'] * 0.78) + (df['kq'] * 0.47)
                # Annualized GDP in Trillion KRW (gdp_q is in Millions)
                df['gdp_annual'] = (df['gdp_q'] / 1000000.0) * 4
                df['buffett'] = (df['mkt_cap'] / df['gdp_annual']) * 100
                
                df_weekly = df.resample('W-FRI').last().dropna()

                data_list = []
                for date, row in df_weekly.iterrows():
                    data_list.append({
                        "ticker": "BUFFET_INDICATOR_KR",
                        "date": date.strftime("%Y-%m-%d"),
                        "value": float(row['buffett']),
                        "created_at": datetime.utcnow().isoformat()
                    })

                if data_list:
                    chunk_size = 500
                    for i in range(0, len(data_list), chunk_size):
                        chunk = data_list[i:i + chunk_size]
                        self.db.client.table("macro_indicators").upsert(chunk, on_conflict="ticker,date").execute()
                    print(f"    [OK] BUFFET_INDICATOR_KR: {len(data_list)} rows processed (KOSPI+KOSDAQ).")
        except Exception as e:
            print(f"    [ERROR] BUFFET_INDICATOR_KR backfill failed: {e}")

    def run_essentials(self):
        """핵심 지표들(CPI, INDPRO 등)만 우선 백필"""
        essentials = ['CPIAUCSL', 'INDPRO', 'PCEPI', 'T10Y2Y', 'DGS10', 'WALCL', '^GSPC', 'GC=F']
        print("=== [ESSENTIAL BACKFILL START] ===")
        for t in essentials:
            if t in self.indicators['FRED']:
                self.backfill_fred_ticker(t)
            else:
                self.backfill_yf_ticker(t)
        print("=== [ESSENTIAL BACKFILL COMPLETE] ===")

    def run_derived(self):
        """파생 지표(순유동성, 버핏지수) 백필"""
        print("=== [DERIVED BACKFILL START] ===")
        self.backfill_net_liquidity()
        self.backfill_buffett_indicator()
        print("=== [DERIVED BACKFILL COMPLETE] ===")

if __name__ == "__main__":
    backfiller = MacroBackfiller()
    backfiller.run_derived()
