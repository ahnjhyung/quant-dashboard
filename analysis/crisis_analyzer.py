"""
Crisis & Bubble Analyzer CDM 3.0 (Ensemble Matrix)
================================================
역사적 위기(닷컴, 리먼, 팬데믹 등) 전조 증상을 30여 개 복합 지표로 분석하여 
'선행-동행-스트레스' 확증 연쇄를 통한 초정밀 위기 진단을 수행합니다.
"""

import pandas as pd
import numpy as np
import logging
from data_collectors.supabase_manager import SupabaseManager
from datetime import datetime, timedelta

class CrisisAnalyzer:
    def __init__(self):
        self.db = SupabaseManager()
        self.logger = logging.getLogger("CrisisAnalyzer")
        logging.basicConfig(level=logging.INFO)

    def _analyze_velocity(self, df: pd.DataFrame, window: int = 3) -> dict:
        """지표의 기울기(Velocity) 및 가속도(Acceleration) 분석"""
        if df is None or len(df) < window + 2:
            return {"slope": 0.0, "accel": 0.0}
        
        values = df['value'].tail(window + 2).values
        slopes = np.diff(values)
        accels = np.diff(slopes)
        
        return {
            "slope": float(slopes[-1]),
            "accel": float(accels[-1]),
            "trend": "UP" if slopes[-1] > 0 else "DOWN"
        }

    def get_leading_layer(self) -> dict:
        """
        Layer 1: Leading Indicators (Weight 60%)
        - Interest/Yields: T10Y3M (Un-inversion Focus), T10Y2Y
        - Real Economy: PERMIT (Construction), AMTMNO (Orders), DGORDER
        - Sentiment: UMCSENT (Consumer), CSCICP03USM665S (OECD CCI)
        - Labor: ICSA (Jobless Claims Momentum)
        """
        scores = {}
        try:
            # 1. Yield Curve Momentum (T10Y3M & T10Y2Y)
            y3m_df = self.db.get_macro_history("T10Y3M", days=500)
            y2y_df = self.db.get_macro_history("T10Y2Y", days=500)
            
            y_score = 0.2
            if y3m_df is not None and not y3m_df.empty:
                curr_y3m = float(y3m_df.iloc[-1]['value'])
                if curr_y3m < 0: y_score = 0.7 # Inverted
                elif 0 <= curr_y3m < 0.3:
                    # Un-inversion Check
                    if y3m_df['value'].tail(90).min() < 0: y_score = 1.0 # CRITICAL
            scores['yield_curve'] = y_score

            # 2. Real Sector Orders (PERMIT & AMTMNO)
            permit_df = self.db.get_macro_history("PERMIT", days=730)
            permit_score = 0.3
            if permit_df is not None and len(permit_df) > 12:
                ma_12 = permit_df['value'].rolling(12).mean().iloc[-1]
                curr = permit_df.iloc[-1]['value']
                permit_score = np.clip((ma_12 - curr) / (ma_12 * 0.1), 0, 1.0)
            scores['real_orders'] = permit_score

            # 3. Sentiment & OECD CLI (UMCSENT & OECD CCI)
            sent_df = self.db.get_macro_history("UMCSENT", days=730)
            cci_df = self.db.get_macro_history("CSCICP03USM665S", days=730)
            sent_score = 0.3
            if sent_df is not None and not sent_df.empty:
                curr_sent = float(sent_df.iloc[-1]['value'])
                sent_score = np.clip((80 - curr_sent) / 30.0, 0, 1.0)
            scores['sentiment'] = sent_score

            # 4. Jobless Claims (ICSA) - Velocity Analysis
            icsa_df = self.db.get_macro_history("ICSA", days=365)
            icsa_score = 0.2
            if icsa_df is not None and len(icsa_df) > 8:
                vel = self._analyze_velocity(icsa_df, window=4)
                # 클레임이 '급증'하기 시작할 때 위험 (가속도가 양수일 때)
                if vel['slope'] > 0 and vel['accel'] > 0: icsa_score = 0.8
                elif vel['slope'] > 0: icsa_score = 0.5
            scores['labor_leading'] = icsa_score

            avg_score = (scores['yield_curve'] * 0.4) + (scores['real_orders'] * 0.2) + \
                        (scores['sentiment'] * 0.2) + (scores['labor_leading'] * 0.2)
            
            return {"score": float(avg_score), "details": scores}
        except Exception as e:
            self.logger.error(f"Leading Layer Error: {e}")
            return {"score": 0.5, "error": str(e)}

    def get_coincident_layer(self) -> dict:
        """
        Layer 2: Coincident Indicators (Weight 30%)
        - Core Stats: PAYEMS (Nonfarm Payrolls), INDPRO (Industrial Production)
        - Demand: M2V (Velocity of Money)
        """
        try:
            # 1. Payrolls Momentum (PAYEMS)
            pay_df = self.db.get_macro_history("PAYEMS", days=730)
            pay_score = 0.2
            if pay_df is not None and len(pay_df) > 6:
                # 6개월 MA 하회 시 사실상 침체 동행
                ma_6 = pay_df['value'].rolling(6).mean().iloc[-1]
                curr = pay_df.iloc[-1]['value']
                if curr < ma_6: pay_score = 0.9
                elif curr < ma_6 * 1.01: pay_score = 0.5
            
            # 2. Industrial Production (INDPRO)
            ind_df = self.db.get_macro_history("INDPRO", days=730)
            ind_score = 0.3
            if ind_df is not None and len(ind_df) > 3:
                vel = self._analyze_velocity(ind_df)
                if vel['trend'] == "DOWN": ind_score = 0.7
            
            avg_score = (pay_score * 0.6) + (ind_score * 0.4)
            return {"score": float(avg_score), "details": {"payrolls": pay_score, "production": ind_score}}
        except Exception as e:
            self.logger.error(f"Coincident Layer Error: {e}")
            return {"score": 0.5, "error": str(e)}

    def get_stress_layer(self) -> dict:
        """
        Layer 3: Sentiment & Financial Stress (Weight 10%)
        - Stress: NFCI, TED Spread, BAMLH0A0HYM2 (Credit Spread)
        - Fear: VIX
        """
        try:
            # 1. Financial Stress (NFCI & TED)
            nfci_df = self.db.get_macro_history("NFCI", days=60)
            nfci_val = float(nfci_df.iloc[-1]['value']) if nfci_df is not None and not nfci_df.empty else 0.0
            nfci_score = np.clip((nfci_val + 0.5) / 1.0, 0, 1.0) # -0.5 ~ 0.5 range

            # 2. Credit Spread (HY Spread)
            hy_df = self.db.get_macro_history("BAMLH0A0HYM2", days=60)
            hy_val = float(hy_df.iloc[-1]['value']) if hy_df is not None and not hy_df.empty else 4.0
            hy_score = np.clip((hy_val - 3.5) / 3.5, 0, 1.0) # 3.5% (Stable) ~ 7.0% (Crisis)

            # 3. Fear Index (VIX)
            vix_df = self.db.get_macro_history("VIXCLS", days=60)
            vix_val = float(vix_df.iloc[-1]['value']) if vix_df is not None and not vix_df.empty else 20.0
            vix_score = np.clip((vix_val - 15) / 25, 0, 1.0) # 15 ~ 40 range

            avg_score = (nfci_score * 0.4) + (hy_score * 0.3) + (vix_score * 0.3)
            return {"score": float(avg_score), "details": {"nfci": nfci_score, "credit": hy_score, "vix": vix_score}}
        except Exception as e:
            self.logger.error(f"Stress Layer Error: {e}")
            return {"score": 0.5, "error": str(e)}

    def analyze_current_market(self):
        """CDM 3.0: 앙상블 초정밀 시장 분석"""
        leading = self.get_leading_layer()
        coincident = self.get_coincident_layer()
        stress = self.get_stress_layer()
        
        # [Ensemble Weighting]
        # 선행지표(60%) + 동행지표(30%) + 스트레스(10%)
        total_risk = (leading['score'] * 0.6) + (coincident['score'] * 0.3) + (stress['score'] * 0.1)
        
        # [Cross-Confirmation Logic]
        # 선행지표만 높고 동행지표(고용/생산)가 버티고 있으면 'Soft Landing' 가능성 부여 (점수 15% 삭감)
        if leading['score'] > 0.7 and coincident['score'] < 0.4:
            total_risk *= 0.85
            confirmation = "DIVERGENCE (Leading High / Coincident Stable)"
        # 선행과 동행이 함께 높으면 'Hard Landing' 확증 (점수 10% 할증)
        elif leading['score'] > 0.7 and coincident['score'] > 0.6:
            total_risk = min(total_risk * 1.1, 1.0)
            confirmation = "CONFIRMED CRASH (All Layers Aligned)"
        else:
            confirmation = "NORMAL CORRELATION"

        print(f"\n{'='*50}")
        print(f" CDM 3.0 ULTRA PRECISION REPORT ")
        print(f"{'='*50}")
        print(f"Overall Risk Score: {total_risk:.2f}")
        print(f"Confirmation State: {confirmation}")
        print("-" * 50)
        print(f"Layer 1 (Leading):  {leading['score']:.2f} | Weight: 60%")
        print(f"Layer 2 (Coincid):  {coincident['score']:.2f} | Weight: 30%")
        print(f"Layer 3 (Stress) :  {stress['score']:.2f} | Weight: 10%")
        print("-" * 50)
        
        status = "NORMAL"
        if total_risk > 0.8: status = "SURVIVAL (FULL EXIT)"
        elif total_risk > 0.6: status = "DANGER (DE-RISKING)"
        elif total_risk > 0.4: status = "CAUTION"
        
        print(f"Final Protocol: {status}")
        print(f"{'='*50}\n")
        
        return {
            "total_risk": total_risk,
            "status": status,
            "confirmation": confirmation,
            "layers": {"leading": leading, "coincident": coincident, "stress": stress}
        }

if __name__ == "__main__":
    analyzer = CrisisAnalyzer()
    analyzer.analyze_current_market()
