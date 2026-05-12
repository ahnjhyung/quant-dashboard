import logging
import sys
from typing import Dict, Any
from data_collectors.supabase_manager import SupabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MacroConsensus")

class MacroConsensusEngine:
    """
    여러 매크로 지표를 종합하여 현재 시장의 투자 컨센서스(매수, 관망, 매도)를 도출하는 엔진.
    """
    def __init__(self):
        self.db = SupabaseManager()

    def _get_trend(self, current: float, prev: float) -> int:
        """이전 대비 증감 방향 리턴: 상승(1), 하락(-1), 동일(0)"""
        if current > prev:
            return 1
        elif current < prev:
            return -1
        return 0

    def analyze_macro_consensus(self) -> Dict[str, Any]:
        """
        Supabase에서 최신 매크로 데이터를 가져와서 점수를 매기고 컨센서스를 반환합니다.
        점수 범위: -100 (극단적 공포/매도) ~ +100 (극단적 낙관/매수)
        """
        macro_data = self.db.get_latest_macro()
        
        # 데이터가 아예 없는 경우 방어 로직
        if not macro_data:
            return {
                "score": 0,
                "consensus": "Data Unavailable",
                "action_plan": "데이터를 불러올 수 없습니다. 동기화 상태를 확인해주세요.",
                "color": "#94a3b8",
                "details": ["[데이터 없음] 데이터 소스(Supabase)에 접근할 수 없거나 데이터가 비어있습니다."]
            }

        # 기본 점수
        score = 0
        details = []

        def get_val(ticker):
            val = macro_data.get(ticker, {}).get("current", None)
            return val if val is not None else None
            
        def get_prev(ticker):
            val = macro_data.get(ticker, {}).get("prev", None)
            return val if val is not None else None

        # 1. 유동성 분석 (Liquidity) - 자산 시장의 연료
        net_liq = get_val("NET_LIQUIDITY")
        fed_assets = get_val("WALCL")
        rrp = get_val("RRPONTSYD")

        liq_score = 0
        if net_liq is not None and get_prev("NET_LIQUIDITY") is not None:
            if net_liq > get_prev("NET_LIQUIDITY"):
                liq_score += 15
                details.append("[강세] 실질 순유동성 증가 (+15점)")
            elif net_liq < get_prev("NET_LIQUIDITY"):
                liq_score -= 10
                details.append("[약세] 실질 순유동성 감소 (-10점)")
                
        if rrp is not None and rrp < 200:
            liq_score -= 5
            details.append("[주의] 역레포(RRP) 버퍼 고갈 임박 (-5점)")
            
        score += liq_score

        # 2. 물가 및 금리 (Inflation & Rates)
        cpi = get_val("CPIAUCSL")
        t10y2y = get_val("T10Y2Y")
        
        inf_score = 0
        if cpi is not None:
            if cpi <= 2.5:
                inf_score += 15
                details.append(f"[강세] 물가 안정권 (CPI {cpi:.2f}%) (+15점)")
            elif cpi >= 3.5:
                inf_score -= 15
                details.append(f"[약세] 높은 물가 수준 (CPI {cpi:.2f}%) (-15점)")
            else:
                inf_score += 5
                details.append(f"[중립] 물가 중립 구간 (CPI {cpi:.2f}%) (+5점)")

        if t10y2y is not None:
            prev_t10y2y = get_prev("T10Y2Y")
            if t10y2y < -0.1:
                inf_score -= 15
                details.append(f"[약세] 장단기 금리 역전 지속 (경기침체 리스크) (-15점)")
            elif t10y2y >= 0 and prev_t10y2y is not None and prev_t10y2y < 0:
                inf_score -= 20
                details.append(f"[약세] 장단기 금리 역전 후 정상화 (침체 현실화 임박) (-20점)")
            elif t10y2y > 0.5:
                inf_score += 10
                details.append(f"[강세] 정상적인 수익률 곡선 (+10점)")

        score += inf_score

        # 3. 고용 및 경기 (Employment & Growth)
        unrate = get_val("UNRATE")
        icsa = get_val("ICSA")
        
        emp_score = 0
        if unrate is not None:
            if unrate <= 4.0:
                emp_score += 15
                details.append(f"[강세] 완전고용 수준 (실업률 {unrate:.1f}%) (+15점)")
            elif unrate >= 4.5:
                emp_score -= 15
                details.append(f"[약세] 고용 둔화/침체 경계 (실업률 {unrate:.1f}%) (-15점)")
                
        if icsa is not None:
            # ICSA는 건수이므로 25만건 기준
            if icsa < 250000:
                emp_score += 10
                details.append(f"[강세] 견조한 주간 고용 (실업수당 {icsa/10000:.1f}만건) (+10점)")
            elif icsa > 300000:
                emp_score -= 10
                details.append(f"[약세] 고용 악화 (실업수당 {icsa/10000:.1f}만건) (-10점)")

        score += emp_score

        # 4. 시장 리스크 및 신용 (Market Risk & Credit)
        vix = get_val("VIXCLS")
        hy_spread = get_val("BAMLH0A0HYM2")
        
        risk_score = 0
        if vix is not None:
            if vix < 15:
                risk_score += 10
                details.append(f"[강세] 매우 안정적인 시장 (VIX {vix:.1f}) (+10점)")
            elif vix > 30:
                risk_score -= 20
                details.append(f"[약세] 극도의 시장 공포 (VIX {vix:.1f}) (-20점)")
                
        if hy_spread is not None:
            if hy_spread < 4.0:
                risk_score += 10
                details.append(f"[강세] 신용 스프레드 안정 ({hy_spread:.2f}%) (+10점)")
            elif hy_spread > 5.5:
                risk_score -= 20
                details.append(f"[약세] 기업 신용 리스크 증가 ({hy_spread:.2f}%) (-20점)")

        score += risk_score

        # 데이터가 부족하여 점수가 0이고 근거도 없는 경우
        if not details:
            details.append("[안내] 판단 근거를 도출하기 위한 최신 매크로 데이터가 부족합니다.")

        # 점수를 -100 ~ 100 범위로 클리핑
        score = max(-100, min(100, score))

        # 컨센서스 판별
        if score >= 40:
            consensus = "Strong Buy (적극 매수)"
            action = "위험자산 비중 확대. 시장 유동성과 펀더멘털이 강력하게 받쳐주는 상승장입니다."
            color = "#10b981" # Green
        elif 10 <= score < 40:
            consensus = "Buy (매수)"
            action = "위험자산 유지 및 선별적 매수. 전반적인 거시 환경이 긍정적입니다."
            color = "#34d399"
        elif -15 <= score < 10:
            consensus = "Hold (관망)"
            action = "포지션 유지 및 리스크 관리. 매크로 방향성이 혼조세를 보이고 있습니다."
            color = "#f59e0b" # Orange
        elif -40 <= score < -15:
            consensus = "Sell (비중 축소)"
            action = "위험자산 비중 축소. 신용 리스크나 경기 둔화 징후가 나타나고 있습니다."
            color = "#ef4444" # Red
        else:
            consensus = "Strong Sell (현금 확보)"
            action = "적극적 현금 확보 및 헷징. 경기 침체나 유동성 위기가 강력히 의심됩니다."
            color = "#b91c1c"

        return {
            "score": score,
            "consensus": consensus,
            "action_plan": action,
            "color": color,
            "details": details
        }

if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
    engine = MacroConsensusEngine()
    result = engine.analyze_macro_consensus()
    print("=== 매크로 컨센서스 분석 결과 ===")
    print(f"총점: {result['score']}/100")
    print(f"의견: {result['consensus']}")
    print(f"액션: {result['action_plan']}")
    print("\n[상세 근거]")
    for d in result['details']:
        print(d)
