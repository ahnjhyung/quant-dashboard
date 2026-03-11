"""
Supabase Database Manager
=========================
수집된 금융 데이터 및 분석 결과를 Supabase에 적재하고 조회하는 모듈
"""

import os
from typing import List, Dict
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY
from datetime import datetime

class SupabaseManager:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            self.client = None
            print("[WARN] [SupabaseManager] URL 또는 Key가 설정되지 않아 비활성화됩니다.")
        else:
            self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    def upsert_asset_metric(self, symbol: str, date: str, metrics: dict):
        """
        특정 자산의 일별 분석 지표 저장
        :param symbol: 티커 (예: AAPL, BTCKRW)
        :param date: 기준 일자 (YYYY-MM-DD)
        :param metrics: 저장할 데이터 딕셔너리 (close_price 등)
        """
        if not self.client:
            return None
        
        data = {
            "symbol": symbol,
            "date": date,
            "created_at": datetime.utcnow().isoformat(),
            **metrics
        }
        
        try:
            # asset_metrics 테이블에 (symbol, date) 기준으로 upsert
            response = self.client.table("asset_metrics").upsert(data, on_conflict="symbol,date").execute()
            return response.data
        except Exception as e:
            print(f"[ERROR] [SupabaseManager] upsert_asset_metric 에러: {e}")
            return None

    def upsert_macro_indicator(self, ticker: str, date: str, value: float):
        """
        거시경제 지표 저장
        :param ticker: FRED 코드 또는 yfinance 티커
        :param date: 기준 일자 (YYYY-MM-DD)
        :param value: 지표 값
        """
        if not self.client:
            return None
        
        data = {
            "ticker": ticker,
            "date": date,
            "value": value,
            "created_at": datetime.utcnow().isoformat()
        }
        
        try:
            # macro_indicators 테이블에 (ticker, date) 기준으로 upsert
            response = self.client.table("macro_indicators").upsert(data, on_conflict="ticker,date").execute()
            return response.data
        except Exception as e:
            print(f"[ERROR] [SupabaseManager] upsert_macro_indicator 에러: {e}")
            return None

    def check_macro_exists(self, ticker: str, date: str) -> bool:
        """특정 날짜에 해당 지표가 이미 DB에 존재하는지 확인"""
        if not self.client:
            return False
        try:
            response = self.client.table("macro_indicators").select("ticker").eq("ticker", ticker).eq("date", date).execute()
            return len(response.data) > 0
        except Exception:
            return False

    def insert_news_events(self, events: list):
        """
        news_scraper에서 파싱한 이벤트(뉴스) 데이터를 고스란히 news_sentiment 테이블에 적재합니다.
        """
        if not self.client or not events:
            return None
            
        data = []
        for i, ev in enumerate(events):
            # 회사명을 심볼에 포함시켜 symbol + date 고유키 제약조건 회피
            safe_ticker = ev['company_name'].replace(" ", "")[:10]
            data.append({
                "symbol": f"EVT_{safe_ticker}_{i}", 
                "title": f"[{ev['keyword']}] {ev['company_name']} - {ev['title']} ({ev.get('pub_date', '')})",
                "sentiment_score": 50, # 기본값
                "buzz_volume": 1,
                "date": datetime.utcnow().strftime('%Y-%m-%d')
            })
            
        try:
            res = self.client.table("news_sentiment").upsert(data, on_conflict="symbol,date").execute()
            print(f"[SupabaseManager] {len(data)}건의 뉴스/공시 이벤트가 적재되었습니다.")
            return res.data
        except Exception as e:
            print(f"[ERROR] [SupabaseManager] insert_news_events 에러: {e}")
            return None

    def get_recent_high_ev_assets(self, limit: int = 10):
        """
        가장 최근 저장된 데이터 중 EV(기대값) 또는 주요 점수가 높은 자산을 가져옵니다.
        notion_reporter에서 사용하기 위한 목적.
        """
        if not self.client:
            return []
            
        try:
            # asset_metrics 테이블에서 최신 데이터 조회 
            response = self.client.table("asset_metrics").select("*").order("created_at", desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            print(f"[ERROR] [SupabaseManager] get_recent_high_ev_assets 에러: {e}")
            return []

    def get_latest_rag_insight(self) -> str:
        """quant_engine이 news_sentiment에 남긴 RAG 브리핑 텍스트 로드"""
        if not self.client:
            return ""
        try:
            response = self.client.table("news_sentiment").select("title").eq("symbol", "RAG_CONTEXT").order("created_at", desc=True).limit(1).execute()
            if response.data:
                return response.data[0].get("title", "")
            return ""
        except Exception as e:
            print(f"[ERROR] [SupabaseManager] get_latest_rag_insight 에러: {e}")
            return ""

    def get_regime_risk_score(self) -> int:
        """quant_engine이 news_sentiment에 남긴 RAG_CONTEXT의 sentiment_score (Regime Risk Score) 조회"""
        if not self.client:
            return 50  # 기본 중립값
        try:
            response = self.client.table("news_sentiment").select("sentiment_score").eq("symbol", "RAG_CONTEXT").order("created_at", desc=True).limit(1).execute()
            if response.data:
                return int(response.data[0].get("sentiment_score", 50))
            return 50
        except Exception as e:
            print(f"[ERROR] [SupabaseManager] get_regime_risk_score 에러: {e}")
            return 50

    def get_macro_history(self, ticker: str, days: int = 400):
        """
        특정 지표의 시계열 데이터를 Pandas DataFrame으로 반환
        """
        if not self.client:
            return None
            
        import pandas as pd
        try:
            response = self.client.table("macro_indicators")\
                .select("date, value")\
                .eq("ticker", ticker)\
                .order("date", desc=True)\
                .limit(days)\
                .execute()
            
            if response.data:
                df = pd.DataFrame(response.data)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                return df.sort_index()
            return pd.DataFrame()
        except Exception as e:
            print(f"[ERROR] [SupabaseManager] get_macro_history 에러: {e}")
            return None

    def get_recent_news_by_ticker(self, ticker: str, days: int = 7) -> List[Dict]:
        """특정 심볼과 관련된 최근 뉴스를 조회"""
        if not self.client:
            return []
        try:
            # symbol 필드에 ticker가 포함되거나 title에 ticker가 포함된 뉴스 조회
            # 실제 데이터 적재 시 symbol에 ticker가 들어있을 것이라 가정
            response = self.client.table("news_sentiment")\
                .select("*")\
                .ilike("title", f"%{ticker}%")\
                .order("created_at", desc=True)\
                .limit(20)\
                .execute()
            return response.data
        except Exception as e:
            print(f"[ERROR] [SupabaseManager] get_recent_news_by_ticker 에러: {e}")
            return []

    def get_recent_global_news(self, days: int = 3) -> List[Dict]:
        """글로벌 뉴스 (Market-wide) 조회"""
        if not self.client:
            return []
        try:
            # 특정 종목에 국한되지 않은 범용 심볼이나 주요 키워드 뉴스 조회
            response = self.client.table("news_sentiment")\
                .select("*")\
                .order("created_at", desc=True)\
                .limit(50)\
                .execute()
            return response.data
        except Exception as e:
            print(f"[ERROR] [SupabaseManager] get_recent_global_news 에러: {e}")
            return []

if __name__ == "__main__":
    # 간단한 테스트
    print("=== SupabaseManager 테스트 ===")
    mgr = SupabaseManager()
    if mgr.client:
        print("[OK] DB 클라이언트 연결 됨")
        # 데이터 1건 임의 적재 테스트 
        test_data = {"close_price": 150.0}
        res = mgr.upsert_asset_metric("TEST_TICKER", datetime.now().strftime("%Y-%m-%d"), test_data)
        print(f"Upsert 결과: {res}")
    else:
        print("[ERROR] DB 연결 실패 - 설정 확인 필요")
