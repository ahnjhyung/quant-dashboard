import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from typing import Optional
from data_collectors.supabase_manager import SupabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MacroCycleAnalyzer")

class MacroCycleAnalyzer:
    """
    Supabase DB에 저장된 매크로 지표를 바탕으로 현재 시장 국면을 판단합니다.
    - API 직접 호출 지양 (data_collectors/macro_data_collector.py 가 수집 전담)
    """
    def __init__(self):
        self.db = SupabaseManager()

    def get_current_regime(self) -> dict:
        """현재 매크로 국면 판정 및 가중치 반환"""
        regime_info = {
            "cycle_state": "NEUTRAL",
            "weight_multiplier": 1.0,
            "details": [],
            "metrics": {}
        }

        try:
            # 1. DB에서 지표 추출
            wti = self.db.get_macro_history("CL=F", days=100)
            unrate = self.db.get_macro_history("UNRATE", days=12)
            cpi = self.db.get_macro_history("CPIAUCSL", days=24)
            spy = self.db.get_macro_history("SPY", days=300)
            hyg = self.db.get_macro_history("HYG", days=100)
            lqd = self.db.get_macro_history("LQD", days=100)

            # 데이터 가용성 체크
            if any(df is None or df.empty for df in [wti, unrate, cpi, spy, hyg, lqd]):
                logger.warning("일부 매크로 데이터가 DB에 없습니다. 데이터 수집기를 먼저 실행하세요.")
                regime_info["details"].append("데이터 부족 (DB 미적재)")
                return regime_info

            # 컬럼명 정리 및 분석용 변수 추출
            wti = wti.rename(columns={'value': 'Close'})
            spy = spy.rename(columns={'value': 'Close'})
            hyg = hyg.rename(columns={'value': 'Close'})
            lqd = lqd.rename(columns={'value': 'Close'})
            unrate_s = unrate['value']
            cpi_s = cpi['value']

            def _get_scalar(series_or_val):
                if hasattr(series_or_val, 'values'):
                    v = series_or_val.values.flatten()
                    return v[-1] if v.size > 0 else 0
                return series_or_val

            # A. 물가 및 에너지 리스크
            current_oil = _get_scalar(wti['Close'])
            oil_ma20 = _get_scalar(wti['Close'].rolling(20).mean())
            oil_spike = bool(current_oil > oil_ma20 * 1.15) if oil_ma20 > 0 else False
            
            cpi_val_curr = cpi_s.iloc[-1]
            cpi_val_prev = cpi_s.iloc[-13] if len(cpi_s) >= 13 else cpi_s.iloc[0]
            cpi_yoy = ((cpi_val_curr / cpi_val_prev) - 1) * 100 if cpi_val_prev != 0 else 0
            is_high_inflation = bool(cpi_yoy > 4.0)
            
            # B. 고용 리스크
            latest_unrate = unrate_s.iloc[-1]
            prev_unrate = unrate_s.iloc[-4] if len(unrate_s) >= 4 else unrate_s.iloc[0]
            is_unrate_rising = bool(latest_unrate > prev_unrate + 0.3)
            
            # C. 금융/시장 리스크
            current_spy = _get_scalar(spy['Close'])
            ma200_spy = _get_scalar(spy['Close'].rolling(200).mean())
            is_market_bull = bool(current_spy > ma200_spy) if ma200_spy > 0 else False
            
            risk_ratio = (hyg['Close'] / lqd['Close'])
            curr_rr = _get_scalar(risk_ratio)
            ma50_rr = _get_scalar(risk_ratio.rolling(50).mean())
            is_risk_on = bool(curr_rr > ma50_rr) if ma50_rr > 0 else False

            # --- 국면 최종 판정 ---
            if (oil_spike or is_high_inflation) and (not is_market_bull or is_unrate_rising):
                regime_info["cycle_state"] = "STAGFLATION"
                regime_info["weight_multiplier"] = 0.55
                regime_info["details"].append(f"에너지/물가 쇼크 (Oil ${current_oil:.1f}, CPI {cpi_yoy:.1f}%)")
            elif is_unrate_rising and not is_market_bull:
                regime_info["cycle_state"] = "RECESSION"
                regime_info["weight_multiplier"] = 0.45
                regime_info["details"].append(f"경기 침체기 진입 가능성 (실업률 {latest_unrate}%)")
            elif is_market_bull and is_risk_on and not is_high_inflation:
                regime_info["cycle_state"] = "GOLDILOCKS"
                regime_info["weight_multiplier"] = 1.25
                regime_info["details"].append("적정 성장 및 리스크 온 국면")
            else:
                regime_info["cycle_state"] = "TRANSITION"
                regime_info["weight_multiplier"] = 0.9
                regime_info["details"].append("지표 혼조세 (관망)")

            regime_info["metrics"] = {
                "oil_spike": oil_spike,
                "cpi_yoy": round(cpi_yoy, 2),
                "unrate": latest_unrate,
                "market_bull": is_market_bull,
                "risk_on": is_risk_on
            }

        except Exception as e:
            logger.error(f"Regime Calculation Error: {e}")
            regime_info["details"].append(f"분석 오류: {e}")

        return regime_info

if __name__ == "__main__":
    analyzer = MacroCycleAnalyzer()
    result = analyzer.get_current_regime()
    print("\n=== 매크로 사이클 평가 결과 (DB 기반) ===")
    print(f"현재 국면: {result['cycle_state']}")
    print(f"가중치(Multiplier): {result['weight_multiplier']}")
    print(f"상세 내역: {result['details']}")
    print(f"핵심 지표: {result['metrics']}")
