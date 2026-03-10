"""
Supabase Database Manager
=========================
수집된 금융 데이터 및 분석 결과를 Supabase에 적재하고 조회하는 모듈
"""

import os
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY
from datetime import datetime

class SupabaseManager:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            self.client = None
            print("[WARN] [SupabaseManager] URL 또는 Key가 설정되지 않아 비활성화됩니다.")
        else:
            self.client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

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
            # asset_metrics 테이블에 (symbol, date) 기준으로 upsert (현재 스키마에 symbol로 되어있음)
            response = self.client.table("asset_metrics").upsert(data, on_conflict="symbol,date").execute()
            return response.data
        except Exception as e:
            print(f"[ERROR] [SupabaseManager] upsert_asset_metric 에러: {e}")
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

    def get_latest_macro(self) -> dict:
        """macro_indicators 테이블에서 최근 수집된 지표들을 현재값(current)과 이전값(prev)으로 묶어 dict로 반환"""
        if not self.client:
            return {}
        try:
            # 추세 반영을 위해 date 기준으로 넉넉하게 200건 로드
            response = self.client.table("macro_indicators").select("ticker, value, date").order("date", desc=True).limit(200).execute()
            macro_dict = {}
            if response.data:
                for row in response.data:
                    ticker = row.get("ticker")
                    val = row.get("value")
                    if ticker and ticker not in macro_dict:
                        macro_dict[ticker] = {"current": val, "prev": val, "history": [val]}
                    elif ticker:
                        macro_dict[ticker]["history"].append(val)
                
                # 이전(Prev) 값 세팅 (가장 최근 대비 약 3~5 영업일 전의 값을 prev로 설정)
                for ticker in macro_dict:
                    hist = macro_dict[ticker]["history"]
                    if len(hist) > 1:
                        idx = min(len(hist) - 1, 5)
                        macro_dict[ticker]["prev"] = hist[idx]
            return macro_dict
        except Exception as e:
            print(f"[ERROR] [SupabaseManager] get_latest_macro 에러: {e}")
            return {}

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
