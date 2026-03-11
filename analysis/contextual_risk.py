"""
Contextual Risk Engine (정성적 리스크 분석기)
=========================================
- 역할: 뉴스, 공시, 매크로 텍스트 데이터를 분석하여 수치화하기 어려운 정성적 리스크 탐지
- 주요 탐지 대상: 유상증자, 지정학적 리스크, 갑작스러운 규제 변화, 유가 등 원자재 쇼크
- 메커니즘: 키워드 스코어링 + 뉴스 감성 분석 결합
"""

import logging
from typing import Dict, List, Optional
from data_collectors.supabase_manager import SupabaseManager
from config import DART_API_KEY

logger = logging.getLogger("ContextualRisk")

class ContextualRiskEngine:
    def __init__(self):
        self.db = SupabaseManager()
        # 리스크 카테고리별 핵심 키워드 및 위험도(0.0 ~ 1.0)
        self.risk_keywords = {
            "FINANCIAL_DISTRESS": {
                "keywords": ["유상증자", "자본잠식", "관리종목", "상장폐지", "의견거절", "CB발행", "전환사채"],
                "base_risk": 0.8
            },
            "GEOPOLITICAL": {
                "keywords": ["전쟁", "침공", "폭격", "미사일", "제재", "봉쇄", "관세", "무역전쟁"],
                "base_risk": 0.6
            },
            "MACRO_SHOCK": {
                "keywords": ["금리인상", "빅스텝", "스테그플레이션", "뱅크런", "유가급등", "오일쇼크"],
                "base_risk": 0.5
            },
            "LEGAL_REGULATORY": {
                "keywords": ["압수수색", "기소", "횡령", "배임", "과징금", "조사착수", "영장"],
                "base_risk": 0.7
            }
        }

    def analyze_ticker_risk(self, ticker: str) -> Dict:
        """
        특정 티커와 관련된 뉴스/공시를 스캔하여 정성적 리스크 점수 산출
        """
        # 1. 최근 7일간의 뉴스/감성 데이터 가져오기 (DB lookup)
        # news_sentiment 테이블에 저장된 뉴스들을 기반으로 분석
        recent_news = self.db.get_recent_news_by_ticker(ticker, days=7)
        
        detected_risks = []
        total_risk_score = 0.0
        
        # 2. 키워드 매칭 분석
        # 예: 티웨이항공 유상증자 사례 방어
        for news in recent_news:
            title = news.get("title", "")
            content = news.get("content", "")
            combined_text = (title + " " + content).replace(" ", "")
            
            for category, config in self.risk_keywords.items():
                matched = [kw for kw in config["keywords"] if kw in combined_text]
                if matched:
                    risk_item = {
                        "category": category,
                        "keywords": matched,
                        "news_title": title[:50] + "...",
                        "severity": config["base_risk"]
                    }
                    detected_risks.append(risk_item)
                    total_risk_score = max(total_risk_score, config["base_risk"])

        # 3. 리스크 배수(Multiplier) 산출
        # Risk Multiplier: 1.0(정상) ~ 0.0(극도로 위험, 거래 금지)
        risk_multiplier = 1.0 - min(0.9, total_risk_score)
        
        # 4. 코멘트 생성 (Explainable AI 관점)
        comment = ""
        if detected_risks:
            top_risk = detected_risks[0]
            comment = f"⚠️ [{top_risk['category']}] 관련 리스크 감지: {', '.join(top_risk['keywords'])} 언급됨. "
            if total_risk_score >= 0.7:
                comment += "기대값이 높아도 보수적인 관점(비중 축소)이 권장됩니다."
        else:
            comment = "✅ 특이 정성적 리스크 발견되지 않음. 수치 기반 전략 유효."

        return {
            "ticker": ticker,
            "risk_score": round(total_risk_score, 2),
            "risk_multiplier": round(risk_multiplier, 2),
            "detected_risks": detected_risks[:3],  # 상위 3개만
            "comment": comment
        }

    def get_global_macro_risk(self) -> Dict:
        """
        시장 전체에 영향을 주는 매크로/지정학 리스크 스캔
        """
        # 키워드 기반 글로벌 뉴스 스캔 (Market-wide)
        global_news = self.db.get_recent_global_news(days=3)
        
        global_detected = []
        max_severity = 0.0
        
        for news in global_news:
            text = news.get("title", "")
            for category, config in self.risk_keywords.items():
                if category in ["GEOPOLITICAL", "MACRO_SHOCK"]:
                    matched = [kw for kw in config["keywords"] if kw in text]
                    if matched:
                        global_detected.append({"category": category, "keywords": matched, "severity": config["base_risk"]})
                        max_severity = max(max_severity, config["base_risk"])
        
        return {
            "global_risk_score": max_severity,
            "global_multiplier": 1.0 - (max_severity * 0.5), # 최대 50% 감쇄
            "summary": f"글로벌 리스크 요인 {len(global_detected)}건 감출" if global_detected else "안정적"
        }

if __name__ == "__main__":
    # 간단한 테스트
    engine = ContextualRiskEngine()
    # DB에 데이터가 있다고 가정하거나 Mock 테스트
    print(engine.analyze_ticker_risk("091810.KS")) # 티웨이항공 예시
