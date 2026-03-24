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

    def get_leading_layer(self, dt: pd.Timestamp = None) -> dict:
        """
        Layer 1: Leading Indicators (Weight 70%)
        - 위기 발생 전 '돈의 흐름'과 '추세'를 포착하는 핵심 엔진
        """
        scores = {}
        try:
            # 1. Yield Curve Momentum (T10Y3M & T10Y2Y)
            y3m_full = self.db.get_macro_history("T10Y3M", days=500)
            y3m_df = y3m_full.loc[:dt] if dt and y3m_full is not None else y3m_full
            y_score = 0.2
            if y3m_df is not None and not y3m_df.empty:
                curr_y3m = float(y3m_df.iloc[-1]['value'])
                if curr_y3m < 0: y_score = 0.8 # Inverted
                elif 0 <= curr_y3m < 0.3:
                    if y3m_df['value'].tail(90).min() < 0: y_score = 1.0 # Un-inversion (대위기 선행)
            scores['yield_curve'] = y_score

            # 2. Net Liquidity (WALCL - RRP)
            walcl = self.db.get_macro_history("WALCL", days=365)
            rrp = self.db.get_macro_history("RRPONTSYD", days=365)
            liq_score = 0.3
            if walcl is not None and rrp is not None:
                liq = walcl['value'] - rrp['value']
                liq_ma = liq.rolling(4).mean()
                if not liq.empty:
                    # 유동성 급감 시 위험 점수 상승
                    liq_score = np.clip((liq_ma.iloc[-1] - liq.iloc[-1]) / (liq_ma.iloc[-1] * 0.05 + 1e-6), 0, 1.0)
            scores['liquidity'] = liq_score

            # 3. Jobless Claims (ICSA) - 실업률보다 빠른 고용 선행지표
            icsa_full = self.db.get_macro_history("ICSA", days=365)
            icsa_df = icsa_full.loc[:dt] if dt and icsa_full is not None else icsa_full
            icsa_score = 0.2
            if icsa_df is not None and len(icsa_df) > 8:
                vel = self._analyze_velocity(icsa_df, window=4)
                if vel['slope'] > 0 and vel['accel'] > 0: icsa_score = 0.9
            scores['labor_leading'] = icsa_score

            avg_score = (scores['yield_curve'] * 0.4) + (scores['liquidity'] * 0.4) + (scores['labor_leading'] * 0.2)
            return {"score": float(avg_score), "details": scores}
        except Exception as e:
            self.logger.error(f"Leading Layer Error: {e}")
            return {"score": 0.5, "error": str(e)}

    def get_coincident_layer(self, dt: pd.Timestamp = None) -> dict:
        """
        Layer 2: Coincident Indicators (Weight 30%)
        """
        try:
            # 1. Payrolls Momentum (PAYEMS)
            pay_full = self.db.get_macro_history("PAYEMS", days=730)
            pay_df = pay_full.loc[:dt] if dt and pay_full is not None else pay_full
            pay_score = 0.2
            if pay_df is not None and len(pay_df) > 6:
                # 6개월 MA 하회 시 사실상 침체 동행
                ma_6 = pay_df['value'].rolling(6).mean().iloc[-1]
                curr = pay_df.iloc[-1]['value']
                if curr < ma_6: pay_score = 0.9
                elif curr < ma_6 * 1.01: pay_score = 0.5
            
            # 2. Industrial Production (INDPRO)
            ind_full = self.db.get_macro_history("INDPRO", days=730)
            ind_df = ind_full.loc[:dt] if dt and ind_full is not None else ind_full
            ind_score = 0.3
            if ind_df is not None and len(ind_df) > 3:
                vel = self._analyze_velocity(ind_df)
                if vel['trend'] == "DOWN": ind_score = 0.7
            
            avg_score = (pay_score * 0.6) + (ind_score * 0.4)
            return {"score": float(avg_score), "details": {"payrolls": pay_score, "production": ind_score}}
        except Exception as e:
            self.logger.error(f"Coincident Layer Error: {e}")
            return {"score": 0.5, "error": str(e)}

    def get_stress_layer(self, dt: pd.Timestamp = None) -> dict:
        """
        Layer 2: Market Stress Index (Weight 30%)
        - 시장 참여자들의 심리적 공포와 신용 경색을 동행 포착
        """
        try:
            # 1. VIX & Dollar Momentum (Dual Fear)
            vix_full = self.db.get_macro_history("VIXCLS", days=60)
            vix_df = vix_full.loc[:dt] if dt and vix_full is not None else vix_full
            vix_val = float(vix_df.iloc[-1]['value']) if vix_df is not None and not vix_df.empty else 20.0
            vix_score = np.clip((vix_val - 15) / 25, 0, 1.0)

            # 2. Credit Spread (HY Spread) - 자금 조달 경색
            hy_full = self.db.get_macro_history("BAMLH0A0HYM2", days=60)
            hy_df = hy_full.loc[:dt] if dt and hy_full is not None else hy_full
            hy_val = float(hy_df.iloc[-1]['value']) if hy_df is not None and not hy_df.empty else 4.0
            hy_score = np.clip((hy_val - 3.5) / 3.5, 0, 1.0)

            avg_score = (vix_score * 0.5) + (hy_score * 0.5)
            return {"score": float(avg_score), "details": {"fear": vix_score, "credit": hy_score}}

            # 3. Fear Index (VIX)
            vix_full = self.db.get_macro_history("VIXCLS", days=60)
            vix_df = vix_full.loc[:dt] if dt and vix_full is not None else vix_full
            vix_val = float(vix_df.iloc[-1]['value']) if vix_df is not None and not vix_df.empty else 20.0
            vix_score = np.clip((vix_val - 15) / 25, 0, 1.0) # 15 ~ 40 range

            # 4. Dollar Index (DXY) - Momentum
            # DXY는 위험자산 하락의 선행/동행 지표
            dxy_full = self.db.get_macro_history("DEXKOUS", days=60) # 임시로 원달러 사용 (DXY 데이터 부족 시 대비)
            dxy_df = dxy_full.loc[:dt] if dt and dxy_full is not None else dxy_full
            dxy_score = 0.3
            if dxy_df is not None and len(dxy_df) > 5:
                # 5일 전 대비 상승 시 위험 증가
                dxy_change = (dxy_df.iloc[-1]['value'] / dxy_df.iloc[-5]['value']) - 1
                dxy_score = np.clip(dxy_change * 20 + 0.3, 0, 1.0) # 2% 상승 시 고점

            avg_score = (nfci_score * 0.3) + (hy_score * 0.3) + (vix_score * 0.2) + (dxy_score * 0.2)
            return {"score": float(avg_score), "details": {"nfci": nfci_score, "credit": hy_score, "vix": vix_score, "dxy": dxy_score}}
        except Exception as e:
            self.logger.error(f"Stress Layer Error: {e}")
            return {"score": 0.5, "error": str(e)}

    def analyze_current_market(self, dt: pd.Timestamp = None):
        """CDM 4.0 (Slim & Strong): 선행-동행-스트레스 3계층 필터링 분석"""
        leading = self.get_leading_layer(dt=dt)
        coincident = self.get_coincident_layer(dt=dt) # 사용자의 요청에 따라 동행지표 유지
        stress = self.get_stress_layer(dt=dt)
        
        # [Ensemble Weighting] 선행(50%) + 동행(30%) + 스트레스(20%)
        # 노이즈 제거를 위해 가중치 재조정
        total_risk = (leading['score'] * 0.5) + (coincident['score'] * 0.3) + (stress['score'] * 0.2)
        
        # [Cross-Confirmation Logic]
        # 선행과 동행이 함께 0.7을 넘으면 '실제 침체(Hard Landing)' 확증
        if leading['score'] > 0.7 and coincident['score'] > 0.6:
            total_risk = min(total_risk * 1.1, 1.0)
            confirmation = "CONFIRMED_CRASH"
        else:
            confirmation = "NORMAL"

        # print(f"\n{'='*50}")
        # print(f" CDM 3.0 ULTRA PRECISION REPORT ")
        # print(f"{'='*50}")
        # print(f"Overall Risk Score: {total_risk:.2f}")
        # print(f"Confirmation State: {confirmation}")
        # print("-" * 50)
        # print(f"Layer 1 (Leading):  {leading['score']:.2f} | Weight: 60%")
        # print(f"Layer 2 (Coincid):  {coincident['score']:.2f} | Weight: 30%")
        # print(f"Layer 3 (Stress) :  {stress['score']:.2f} | Weight: 10%")
        # print("-" * 50)
        
        status = "NORMAL"
        if total_risk > 0.8: status = "SURVIVAL (FULL EXIT)"
        elif total_risk > 0.6: status = "DANGER (DE-RISKING)"
        elif total_risk > 0.4: status = "CAUTION"
        
        # print(f"Final Protocol: {status}")
        # print(f"{'='*50}\n")
        
        return {
            "total_risk": total_risk,
            "status": status,
            "confirmation": confirmation,
            "layers": {"leading": leading, "coincident": coincident, "stress": stress}
        }

if __name__ == "__main__":
    analyzer = CrisisAnalyzer()
    analyzer.analyze_current_market()
