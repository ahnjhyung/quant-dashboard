import os
import json
import requests
import google.generativeai as genai
from datetime import datetime
from vector_store import VectorMemory
from data_collectors.un_comtrade import UNComtradeCollector
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY, GEMINI_API_KEY

# ==========================================
# CONFIGURATION
# ==========================================
# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)

class QuantEngine:
    def __init__(self):
        print("--- [Quant Engine] Booting up ---")
        self.headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        self.memory = VectorMemory()
        self.trade_collector = UNComtradeCollector()

    def fetch_latest_market_data(self):
        """
        Fetches the latest assets and macro indicators from Supabase via REST API.
        """
        try:
            # 1. Fetch latest asset prices (Limit 20 for brief analysis)
            url_assets = f"{SUPABASE_URL}/rest/v1/asset_metrics?select=*&order=date.desc&limit=20"
            res_assets = requests.get(url_assets, headers=self.headers)
            res_assets.raise_for_status()

            # 2. Fetch latest macro indicators
            url_macro = f"{SUPABASE_URL}/rest/v1/macro_indicators?select=*&order=date.desc&limit=30"
            res_macro = requests.get(url_macro, headers=self.headers)
            res_macro.raise_for_status()
            
            return {
                "assets": res_assets.json(),
                "macro": res_macro.json()
            }
        except Exception as e:
            print(f"❌ Supabase Fetch Error (REST API): {e}")
            return {"assets": [], "macro": []}

    def generate_daily_summary(self, market_data) -> str:
        """
        Converts the raw data into a text summary representing today's "state".
        This text is what gets turned into a Vector Embedding in ChromaDB.
        """
        macro = market_data.get("macro", [])
        news = market_data.get("news", [])
        
        # Helper to extract value
        def get_val(ticker):
            for m in macro:
                if m['ticker'] == ticker:
                    return float(m['value'])
            return 0.0

        vix = get_val('VIXCLS')
        fx = get_val('DEXKOUS')
        cpi = get_val('CPALTT01USM657N')
        fed_funds = get_val('FEDFUNDS')
        
        # Calculate Net Liquidity (simplified)
        walcl = get_val('WALCL') / 1000  # Billions
        wtregen = get_val('WTREGEN') / 1000
        rrp = get_val('RRPONTSYD')
        net_liq = walcl - wtregen - rrp

        summary = (
            f"Market State: VIX is at {vix}. USD/KRW Exchange Rate is {fx}. "
            f"Net Liquidity is roughly ${net_liq:,.0f} Billion. "
            f"US CPI stands around {cpi}%. Federal Funds Rate is {fed_funds}%."
        )

        # Inject Top 3 News Headlines into the embedding to capture "Sentiment"
        if news:
            top_headlines = [n.get('title', '') for n in news[:3] if 'title' in n]
            if top_headlines:
                summary += f" Recent News: {' | '.join(top_headlines)}"

        return summary

    def generate_ai_briefing(self, today_summary: str, similar_past: list, market_data: dict) -> str:
        """
        [NEW] Calls Gemini API to generate a high-quality "Daily Quant Briefing" 
        based on today's summary, past RAG scenarios, and raw macro data.
        """
        print("[LLM] Generating professional analyst briefing via Gemini...")
        
        # Prepare context payload
        context_str = f"## 1. Today's Core Market State\n{today_summary}\n\n"
        
        context_str += "## 2. Past Similar Regimes (Vector RAG Matches)\n"
        if similar_past:
            for idx, match in enumerate(similar_past):
                context_str += f"[{idx+1}] Date: {match.get('date')} (Distance: {match.get('distance')})\n"
                context_str += f"    Situation: {match.get('summary')}\n"
        else:
            context_str += "No significant historical precedents found.\n"
            
        context_str += "\n## 3. Latest Key Macro Indicators\n"
        macro = market_data.get("macro", [])
        for m in macro[:10]: # limit to top 10 important ones to save token space
            context_str += f"- {m.get('ticker')}: {m.get('value')} (Recorded at {m.get('date')})\n"

        context_str += "\n## 4. Global Trade Flows (UN Comtrade)\n"
        trade_data = market_data.get("trade", [])
        if trade_data:
            for t in trade_data:
                context_str += f"- {t['reporter']} -> {t['partner']} ({t['commodity']}): ${t['value_usd']:,.0f} USD ({t['year']})\n"
        else:
            context_str += "No recent UN Comtrade data fetched.\n"

        prompt = f"""
너는 최고 수준의 월스트리트 매크로 퀀트 애널리스트야.
아래에 제공된 '오늘의 시장 상태', '과거 유사 사례(RAG 벡터 검색 매칭 기록)', '가장 최근에 수집된 거시경제(Macro) 지표 데이터'를 바탕으로 "초고품질 투자 통찰이 담긴 데일리 브리핑 뉴스레터 텍스트"를 작성해.

[지시문/형식 가이드]
이 양식의 목차를 정확히 따라 써줘. 블록 기호나 불필요한 마크다운 꾸밈은 최소화하고 가독성을 높여. (나중에 노션에 삽입될 거야.)

1. 현재 시장 뷰 1줄 문장 요약 (A vs B 식의 디커플링이나 안전/위험자산 흐름을 관통하는 한 줄)
2. A. 자산 간 상관관계 및 디커플링 진단: 현재 주식, 채권, 외환시장이 따로 노는지, 같이 움직이는지에 대한 코멘트 (1문단)
3. B. 리스크 점검 (과거 유사 사례 분석): 내가 제공한 "2. Past Similar Regimes" 사례들과 현재 상황을 비교하여, 유동성 경색이나 위기 전이 가능성에 대해 논평해줘. (1~2문단)
4. C. 주요 거시 지표 모니터링 가이드: 환율(DEXKOUS), VIX(VIXCLS), 금리(FEDFUNDS) 중 의미있는 변화치가 있다면 콕 짚어 경고/코멘트 (2~3개 불릿포인트)

[데이터]
{context_str}
"""
        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"[ERROR] Gemini Generation Error: {e}")
            return "애널리스트 브리핑(LLM) 생성 중 오류가 발생했습니다. (API 확인 필요)"

    def run_rag_pipeline(self):
        """
        Main pipeline step.
        1. Fetch data
        2. Create summary for today
        3. Search ChromaDB for similar past summaries
        4. Save today's summary to ChromaDB
        5. Push the RAG context back to Supabase for the GAS Reporter to read
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        print(f"\n[1] Fetching market data for {today_str}...")
        market_data = self.fetch_latest_market_data()
        
        print("[1.1] Fetching Global Trade Data (UN Comtrade)...")
        # Fetch Korea -> US Semiconductor export as a key sample
        try:
            trade_sample = self.trade_collector.get_trade_flows('410', '842', '8542', datetime.now().year - 2, 'X')
            market_data["trade"] = trade_sample
        except:
            market_data["trade"] = []

        print("[2] Generating market state summary...")
        today_summary = self.generate_daily_summary(market_data)
        print(f"    Today's State: {today_summary}")

        print("[3] Searching Vector Memory for similar past situations...")
        # Search for top 3 similar past days (Dynamic accumulated history)
        similar_past = self.memory.recall_similar_situations(today_summary, k=3)
        
        rag_context_text = "### 과거 벡터 유사도 시나리오 (Supabase pgvector)\n"
        if similar_past:
            print("    Found historical matches!")
            for idx, match in enumerate(similar_past):
                # Avoid matching exactly with today's own summary if it was already saved
                if match['date'] == today_str:
                    continue
                rag_context_text += f"\n- **[사례 {idx+1}] 날짜: {match['date']}** (유사도 거리: {match['distance']})\n"
                rag_context_text += f"  - 당시 상황: {match['summary']}\n"
        else:
            rag_context_text += "- 단순 유사 과거 사례 없음 (데이터 축적 중)\n"

        print("[4] Memorizing today's state into Supabase pgvector...")
        self.memory.save_daily_memory(
            date_str=today_str,
            market_summary_text=today_summary,
            metadata={"source": "quant_engine_auto"}
        )

        print("[5] Generating Analyst Insight Briefing with LLM...")
        # 기존 단순 텍스트 합치기 대신 Gemini가 쓴 고품질 글(Insight) 획득
        analyst_briefing = self.generate_ai_briefing(today_summary, similar_past, market_data)

        print("[6] Uploading AI RAG Insights to Supabase (Using news_sentiment table as text carrier)...")
        try:
            # We push the RAG Insight into the `news_sentiment` table because it has a text `title` column!
            payload = {
                "date": today_str,
                "symbol": "RAG_CONTEXT",
                "sentiment_score": 0,
                "buzz_volume": len(similar_past),
                "title": analyst_briefing 
            }
            
            upsert_headers = self.headers.copy()
            upsert_headers["Prefer"] = "return=representation,resolution=merge-duplicates"
            
            # Upsert into news_sentiment using date and symbol as conflict keys
            url_upsert = f"{SUPABASE_URL}/rest/v1/news_sentiment?on_conflict=date,symbol"
            res = requests.post(url_upsert, headers=upsert_headers, json=[payload])
            res.raise_for_status()
            
            print("--- [OK] [Quant Engine] RAG Pipeline Completed Successfully ---")

        except Exception as e:
            print(f"[ERROR] Failed to upload RAG Insight to Supabase (REST API): {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")

if __name__ == "__main__":
    engine = QuantEngine()
    engine.run_rag_pipeline()
