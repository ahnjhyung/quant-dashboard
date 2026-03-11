"""
페어 트레이딩 (상대계수 및 공적분) 분석 엔진
===============================================
- 두 자산(종목 vs 종목 / 종목 vs 매크로지표) 간의 공적분(Cointegration) 검정
- OLS 선형회귀를 통한 헤지 비율(Hedge Ratio) 산출
- 스프레드 Z-Score 기반의 상대적 가치 평가 및 매매 신호
- 시장 중립적(Market Neutral) 차익거래 모델
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint
from data_collectors.supabase_manager import SupabaseManager

class PairsTradingAnalyzer:
    """
    상대계수 및 공적분을 이용한 통계적 차익거래 분석기
    """
    def __init__(self):
        self.db = SupabaseManager()

    def get_yfinance_data(self, ticker: str, period: str = "1y") -> pd.Series:
        """yfinance에서 OHLCV 다운로드 후 Close 종가 시계열 반환"""
        try:
            df = yf.download(ticker, period=period, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df['Close'].dropna()
        except Exception as e:
            print(f"[ERROR] {ticker} 데이터 다운로드 실패: {e}")
            return pd.Series(dtype=float)

    def analyze_pair(self, ticker_y: str, ticker_x: str, period: str = "2y") -> dict:
        """
        [종목 vs 종목] 공적분 페어 트레이딩 분석
        :param ticker_y: 종속 변수 (가격 변동을 쫓아갈 자산, 예: KB금융)
        :param ticker_x: 독립 변수 (기준 자산, 예: 신한지주)
        """
        print(f"[INFO] [{ticker_y}] vs [{ticker_x}] 페어 트레이딩 분석 중...")
        
        series_y = self.get_yfinance_data(ticker_y, period)
        series_x = self.get_yfinance_data(ticker_x, period)
        
        if series_y.empty or series_x.empty:
            return {'error': '데이터를 충분히 확보하지 못했습니다.'}
            
        return self._run_cointegration_analysis(series_y, series_x, ticker_y, ticker_x)
        
    def analyze_macro_pair(self, ticker_y: str, macro_ticker: str) -> dict:
        """
        [종목 vs 매크로] Supabase 매크로 지표와 종목 간 상대계수 연동 분석
        """
        print(f"[INFO] [{ticker_y}] vs 매크로[{macro_ticker}] 상대계수 분석 중...")
        
        # 1. Yfinance에서 종목 로드
        series_y = self.get_yfinance_data(ticker_y, period="1y")
        
        # 2. Supabase에서 매크로(X) 로드
        if not self.db.client:
            return {'error': 'Supabase 연결 실패'}
            
        try:
            # macro_indicators 테이블에서 해당 지표 데이터 조회
            res = self.db.client.table("macro_indicators").select("date,value").eq("ticker", macro_ticker).order("date", desc=True).limit(300).execute()
            if not res.data:
                return {'error': f'{macro_ticker} 매크로 데이터 없음'}
                
            macro_df = pd.DataFrame(res.data)
            macro_df['date'] = pd.to_datetime(macro_df['date'])
            macro_df.set_index('date', inplace=True)
            macro_df.sort_index(inplace=True)
            series_x = macro_df['value']
        except Exception as e:
            return {'error': f'매크로 데이터 로드 실패: {e}'}
            
        return self._run_cointegration_analysis(series_y, series_x, ticker_y, macro_ticker)

    def _run_cointegration_analysis(self, series_y: pd.Series, series_x: pd.Series, name_y: str, name_x: str) -> dict:
        """핵심 OLS 통계 처리 및 공적분 / Z-Score 계산, EV 산출 로직"""
        # 1. 두 시계열 날짜 인덱스 교집합 추출 
        # (매크로는 공휴일이 제외되거나 업데이트 간격이 다를 수 있음)
        series_y.index = pd.to_datetime(series_y.index).normalize()
        series_x.index = pd.to_datetime(series_x.index).normalize()
        
        df = pd.concat([series_y, series_x], axis=1, join='inner').dropna()
        df.columns = ['Y', 'X']
        
        if len(df) < 60:
            return {'error': f'교집합이 존재하는 유효 데이터가 부족합니다: {len(df)}일 (최소 60일 권장)'}
            
        y = df['Y']
        x = df['X']
        
        # 2. 통계적 기반: Cointegration (공적분) 검정
        # p-value < 0.05 이면 두 이질적 시계열 간의 스프레드가 결국 평균으로 회귀함
        score, pvalue, _ = coint(y, x)
        is_cointegrated = bool(pvalue < 0.05)
        
        # 3. OLS 선형회귀를 통한 Hedge Ratio (Beta) 산출
        x_with_const = sm.add_constant(x)
        model = sm.OLS(y, x_with_const).fit()
        beta = model.params['X']
        alpha = model.params['const']
        
        # 4. Spread 잔차 추적 및 Z-Score (최근 20일 기준 상대적 괴리율 정규화)
        spread = y - (beta * x + alpha)
        spread_mean = spread.rolling(window=20).mean()
        spread_std = spread.rolling(window=20).std()
        
        # 0 나누기 방어
        z_score = np.where(spread_std > 0, (spread - spread_mean) / spread_std, 0)
        current_z = float(z_score[-1])
        
        # 5. 매수 전용(Long-only) 신호 판별
        # - 스프레드 > +2σ : Y가 상대 고평가 → X(저평가) 매수
        # - 스프레드 < -2σ : Y가 상대 저평가 → Y 매수
        # 공매도 없이 '더 싼 쪽을 사는' 전략만 사용
        cheaper_ticker = name_x  # z>0이면 X가 상대적으로 저렴
        pricier_ticker = name_y

        if current_z >= 2.0:
            signal = "BUY_X"   # X 매수 (Y 대비 저평가)
            reason = (f"Z={current_z:.2f}: {name_y} 상대 고평가 —"
                      f" ▶ {name_x}(저평가) 매수 후 스프레드 수렴 기대")
        elif current_z <= -2.0:
            signal = "BUY_Y"   # Y 매수 (X 대비 저평가)
            reason = (f"Z={current_z:.2f}: {name_y} 상대 저평가 —"
                      f" ▶ {name_y}(저평가) 매수 후 스프레드 수렴 기대")
        else:
            signal = "HOLD"
            reason = f"정상 궤도 내 (Z-Score {current_z:.2f}) — 아직 진입 기준 미달"

        # 6. 공적분 검증 (거짓 신호 방어)
        base_win_prob = 0.5
        if is_cointegrated:
            if abs(current_z) >= 2.0:
                # p-value가 작을수록(공적분 강할수록) 회귀 신뢰도 상승
                base_win_prob = 0.70 + max(0, (0.05 - pvalue)) * 4.0
        else:
            base_win_prob = 0.35
            if signal != "HOLD":
                signal = "AVOID"
                reason = "Z-Score 이탈했으나 공적분 관계 없음 → 거짓 신호 (AVOID)"

        win_prob = min(max(base_win_prob, 0.1), 0.95)
        lose_prob = 1.0 - win_prob

        # 7. EV 산출: 2σ 회귀 목표 수익 vs 3.5σ 도달 시 손절
        last_y = float(y.iloc[-1])
        last_x = float(x.iloc[-1])
        std_val = float(spread_std.iloc[-1]) if not np.isnan(spread_std.iloc[-1]) else 0.0

        # 매수 대상 자산 기준 수익률 계산
        buy_price = last_x if signal == "BUY_X" else last_y
        avg_profit_pct = abs(2.0 * std_val / buy_price) if buy_price > 0 else 0.0
        avg_loss_pct   = abs(1.5 * std_val / buy_price) if buy_price > 0 else 0.0

        expected_value_pct = (win_prob * avg_profit_pct) - (lose_prob * avg_loss_pct)

        return {
            "pair":              f"{name_y} vs {name_x}",
            "ticker_y":          name_y,
            "ticker_x":          name_x,
            "is_cointegrated":   is_cointegrated,
            "coint_pvalue":      round(float(pvalue), 4),
            "correlation":       round(float(y.corr(x)), 4),
            "hedge_ratio_beta":  round(float(beta), 4),
            "current_z_score":   round(current_z, 2),
            "signal":            signal,
            "buy_target":        name_x if signal == "BUY_X" else (name_y if signal == "BUY_Y" else None),
            "reason":            reason,
            "risk_metrics": {
                "win_probability":     round(float(win_prob), 3),
                "avg_profit_pct":      round(float(avg_profit_pct), 4),
                "avg_loss_pct":        round(float(avg_loss_pct), 4),
                "expected_value_pct":  round(float(expected_value_pct), 4),
            },
            "prices": {
                name_y: round(last_y, 4),
                name_x: round(last_x, 4),
            },
        }

if __name__ == "__main__":
    analyzer = PairsTradingAnalyzer()
    
    print("=== [테스트 1] 암호화폐 짝꿍: 비트 vs 이더 ===")
    res1 = analyzer.analyze_pair("BTC-USD", "ETH-USD", "2y")
    print(res1)
    
    print("\n=== [테스트 2] 한국 금융지주 종목 간 상관관계 ===")
    res2 = analyzer.analyze_pair("105560.KS", "055550.KS", "2y") # KB금융 vs 신한지주
    print(res2)
