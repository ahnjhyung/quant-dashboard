"""
스윙 트레이딩 기술적 분석 엔진
================================
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- 볼린저밴드 (Bollinger Bands)
- 일목균형표 (Ichimoku Cloud)
- 패턴 감지 (골든크로스, 데드크로스, 과매수/과매도)
- 통합 스윙 신호 생성
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional


class SwingTradingAnalyzer:
    """
    스윙 트레이딩 기술적 분석기
    
    Usage:
        analyzer = SwingTradingAnalyzer()
        result = analyzer.full_analysis("AAPL")
        signal = analyzer.swing_signal_composite("005930.KS", period="6mo")
    """

    def __init__(self):
        pass

    def get_ohlcv(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Yahoo Finance에서 OHLCV 데이터 다운로드
        
        Args:
            ticker: 티커 ('AAPL', '005930.KS' 등)
            period: '1mo', '3mo', '6mo', '1y', '2y', '5y'
            interval: '1d', '1wk', '1mo'
        """
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.dropna()
            return df
        except Exception as e:
            print(f"❌ OHLCV 다운로드 실패 [{ticker}]: {e}")
            return pd.DataFrame()

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """
        RSI (Relative Strength Index) 계산
        
        - RSI < 30: 과매도 (매수 신호)
        - RSI > 70: 과매수 (매도 신호)
        - RSI 50: 중립
        """
        delta = prices.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
        avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
        
        rs = avg_gain / avg_loss.replace(0, np.inf)
        rsi = 100 - (100 / (1 + rs))
        return rsi.round(2)

    def calculate_macd(
        self,
        prices: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> tuple:
        """
        MACD (Moving Average Convergence Divergence) 계산
        
        - MACD Line = EMA(12) - EMA(26)
        - Signal Line = EMA(9) of MACD
        - Histogram = MACD - Signal
        
        Returns:
            (macd_line, signal_line, histogram) as pd.Series
        """
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line.round(4), signal_line.round(4), histogram.round(4)

    def bollinger_bands(
        self,
        prices: pd.Series,
        period: int = 20,
        std_dev: float = 2.0
    ) -> tuple:
        """
        볼린저밴드 계산
        
        - Upper Band = SMA(20) + 2σ
        - Middle Band = SMA(20)
        - Lower Band = SMA(20) - 2σ
        
        Returns:
            (upper, middle, lower, bandwidth, %B) as pd.Series
        """
        middle = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        bandwidth = ((upper - lower) / middle * 100).round(2)
        pct_b = ((prices - lower) / (upper - lower)).round(4)
        
        return upper.round(2), middle.round(2), lower.round(2), bandwidth, pct_b

    def ichimoku_cloud(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        일목균형표 (Ichimoku Cloud) 계산
        
        - 전환선 (Tenkan-sen): 9일 최고+최저 / 2
        - 기준선 (Kijun-sen): 26일 최고+최저 / 2
        - 선행스팬A (Senkou A): (전환 + 기준) / 2, 26일 선행
        - 선행스팬B (Senkou B): 52일 최고+최저 / 2, 26일 선행
        - 후행스팬 (Chikou): 현재 종가, 26일 후행
        
        Returns:
            DataFrame with Ichimoku columns
        """
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        # 전환선
        tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
        # 기준선
        kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
        # 선행스팬A
        senkou_a = ((tenkan + kijun) / 2).shift(26)
        # 선행스팬B
        senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
        # 후행스팬
        chikou = close.shift(-26)
        
        df = df.copy()
        df['Tenkan'] = tenkan.round(2)
        df['Kijun'] = kijun.round(2)
        df['Senkou_A'] = senkou_a.round(2)
        df['Senkou_B'] = senkou_b.round(2)
        df['Chikou'] = chikou.round(2)
        df['Cloud_Color'] = np.where(senkou_a > senkou_b, 'green', 'red')
        
        return df

    def calculate_stochastic(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> tuple:
        """스토캐스틱 오실레이터"""
        lowest_low = df['Low'].rolling(k_period).min()
        highest_high = df['High'].rolling(k_period).max()
        k = ((df['Close'] - lowest_low) / (highest_high - lowest_low) * 100).round(2)
        d = k.rolling(d_period).mean().round(2)
        return k, d

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        ATR (Average True Range) - 변동성 측정
        손절가 설정에 활용: 진입가 ± 2×ATR
        """
        high = df['High']
        low = df['Low']
        close = df['Close']
        prev_close = close.shift(1)
        
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        
        return tr.ewm(com=period-1, adjust=False).mean().round(2)

    def calculate_volume_signal(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        거래량 신호: 거래량이 평균 대비 2배 이상이면 강한 신호
        """
        avg_vol = df['Volume'].rolling(period).mean()
        vol_ratio = df['Volume'] / avg_vol
        return vol_ratio.round(2)

    def calculate_ema(self, prices: pd.Series, period: int = 200) -> pd.Series:
        """지수이동평균(EMA) 계산"""
        return prices.ewm(span=period, adjust=False).mean().round(2)

    def detect_golden_dead_cross(self, prices: pd.Series) -> dict:
        """
        골든크로스 / 데드크로스 및 200 EMA 추세 감지
        """
        ma50 = prices.rolling(50).mean()
        ma200 = prices.rolling(200).mean()
        ema200 = self.calculate_ema(prices, 200)
        
        prev_diff = (ma50 - ma200).shift(1)
        curr_diff = ma50 - ma200
        
        golden_cross = (prev_diff < 0) & (curr_diff > 0)
        dead_cross = (prev_diff > 0) & (curr_diff < 0)
        
        latest_golden = golden_cross.index[golden_cross][-1] if golden_cross.any() else None
        latest_dead = dead_cross.index[dead_cross][-1] if dead_cross.any() else None
        
        current_price = prices.iloc[-1]
        current_ema200 = ema200.iloc[-1]
        
        return {
            'ma50': round(ma50.iloc[-1], 2) if not pd.isna(ma50.iloc[-1]) else None,
            'ma200': round(ma200.iloc[-1], 2) if not pd.isna(ma200.iloc[-1]) else None,
            'ema200': current_ema200,
            'price_above_ema200': current_price > current_ema200,
            'ma50_above_ma200': ma50.iloc[-1] > ma200.iloc[-1] if not (pd.isna(ma50.iloc[-1]) or pd.isna(ma200.iloc[-1])) else None,
            'last_golden_cross': str(latest_golden.date()) if latest_golden is not None else None,
            'last_dead_cross': str(latest_dead.date()) if latest_dead is not None else None,
            'trend_status': 'LONG-TERM BULLISH' if current_price > current_ema200 else 'LONG-TERM BEARISH'
        }

    def full_analysis(self, ticker: str, period: str = "1y") -> dict:
        """
        종합 기술적 분석 (모든 지표 포함)
        
        Returns:
            {
                'ticker': ...,
                'current_price': ...,
                'rsi': ...,
                'macd': {...},
                'bollinger': {...},
                'ichimoku': {...},
                'signals': {...},
                'swing_signal': 'BUY' | 'SELL' | 'HOLD',
                'confidence': 0.75,
            }
        """
        df = self.get_ohlcv(ticker, period=period)
        if df.empty:
            return {'error': f'{ticker} 데이터 없음'}
        
        close = df['Close']
        current_price = float(close.iloc[-1])
        
        # === 지표 계산 ===
        rsi = self.calculate_rsi(close)
        macd_line, signal_line, histogram = self.calculate_macd(close)
        upper, middle, lower, bw, pct_b = self.bollinger_bands(close)
        atr = self.calculate_atr(df)
        vol_ratio = self.calculate_volume_signal(df)
        
        # 최신값 추출
        latest_rsi = float(rsi.iloc[-1])
        latest_macd = float(macd_line.iloc[-1])
        latest_signal = float(signal_line.iloc[-1])
        latest_hist = float(histogram.iloc[-1])
        latest_upper = float(upper.iloc[-1])
        latest_middle = float(middle.iloc[-1])
        latest_lower = float(lower.iloc[-1])
        latest_bw = float(bw.iloc[-1])
        latest_pct_b = float(pct_b.iloc[-1])
        latest_atr = float(atr.iloc[-1])
        latest_vol_ratio = float(vol_ratio.iloc[-1])
        
        cross = self.detect_golden_dead_cross(close)
        
        # === 신호 분석 ===
        signals = {}
        bull_votes = 0
        bear_votes = 0
        
        # 200 EMA 트렌드 필터 (필수 조건)
        is_bullish_trend = cross.get('price_above_ema200', False)
        
        # RSI 신호
        if latest_rsi < 30:
            if is_bullish_trend:
                signals['RSI'] = {'signal': 'STRONG_BUY', 'value': latest_rsi, 'reason': '200 EMA 위 + RSI 과매도 (눌림목)'}
                bull_votes += 3
            else:
                signals['RSI'] = {'signal': 'BUY', 'value': latest_rsi, 'reason': 'RSI 과매도 (역추세 매수 주의)'}
                bull_votes += 1
        elif latest_rsi > 70:
            signals['RSI'] = {'signal': 'SELL', 'value': latest_rsi, 'reason': 'RSI 과매수 (청산 고려)'}
            bear_votes += 2
        
        # MACD 신호
        prev_hist = float(histogram.iloc[-2]) if len(histogram) > 1 else 0
        if latest_hist > 0 and prev_hist < 0:
            if is_bullish_trend:
                signals['MACD'] = {'signal': 'STRONG_BUY', 'value': latest_hist, 'reason': '상승추세 중 MACD 상향 돌파'}
                bull_votes += 2
            else:
                signals['MACD'] = {'signal': 'BUY', 'value': latest_hist, 'reason': 'MACD 상향 돌파'}
                bull_votes += 1
        
        # 볼린저밴드 신호
        if latest_pct_b < 0.05:
            if is_bullish_trend:
                signals['Bollinger'] = {'signal': 'STRONG_BUY', 'value': latest_pct_b, 'reason': '상승추세 중 밴드 하단 터치 (절호의 기회)'}
                bull_votes += 2
            else:
                signals['Bollinger'] = {'signal': 'WATCH', 'value': latest_pct_b, 'reason': '하락추세 중 밴드 하단 (추가 하락 가능성)'}
        elif latest_pct_b > 0.95:
            signals['Bollinger'] = {'signal': 'SELL', 'value': latest_pct_b, 'reason': '상단밴드 터치 (고점 저항)'}
            bear_votes += 2
        
        # 200 EMA 필터 가점
        if is_bullish_trend:
            bull_votes += 1
        else:
            bear_votes += 2  # 하락 추세에서는 매수 보수적 접근
        
        # 거래량 신호
        if latest_vol_ratio > 2.0:
            signals['Volume'] = {'signal': 'ALERT', 'value': latest_vol_ratio, 'reason': f'거래량 폭발 ({latest_vol_ratio:.1f}배)'}
            if is_bullish_trend and latest_hist > 0:
                bull_votes += 1
        
        # === 최종 신호 결정 ===
        total_votes = bull_votes + bear_votes
        if total_votes > 0:
            bull_ratio = bull_votes / total_votes
        else:
            bull_ratio = 0.5
        
        if bull_ratio >= 0.65:
            final_signal = 'BUY 🟢'
            confidence = min(0.95, bull_ratio)
        elif bull_ratio <= 0.35:
            final_signal = 'SELL 🔴'
            confidence = min(0.95, 1 - bull_ratio)
        else:
            final_signal = 'HOLD 🟡'
            confidence = abs(bull_ratio - 0.5) * 2
        
        # 손절/목표가 (ATR 기반)
        stop_loss = round(current_price - 2 * latest_atr, 2)
        target_price = round(current_price + 3 * latest_atr, 2)
        risk_reward = round((target_price - current_price) / (current_price - stop_loss), 2) if current_price > stop_loss else 0
        
        return {
            'ticker': ticker,
            'current_price': round(current_price, 2),
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'rsi': {'value': latest_rsi, 'signal': signals.get('RSI', {}).get('signal', '')},
            'macd': {
                'macd_line': latest_macd,
                'signal_line': latest_signal,
                'histogram': latest_hist,
                'signal': signals.get('MACD', {}).get('signal', ''),
            },
            'bollinger': {
                'upper': latest_upper,
                'middle': latest_middle,
                'lower': latest_lower,
                'bandwidth': latest_bw,
                'pct_b': latest_pct_b,
                'signal': signals.get('Bollinger', {}).get('signal', ''),
            },
            'ma_cross': cross,
            'atr': latest_atr,
            'volume_ratio': latest_vol_ratio,
            'signals': signals,
            'swing_signal': final_signal,
            'confidence': round(confidence, 2),
            'bull_votes': bull_votes,
            'bear_votes': bear_votes,
            'risk_management': {
                'entry': current_price,
                'stop_loss': stop_loss,
                'target': target_price,
                'risk_reward_ratio': risk_reward,
                'risk_pct': round((current_price - stop_loss) / current_price * 100, 2),
            },
            'ohlcv': df,
        }

    def swing_signal_composite(self, ticker: str, period: str = "6mo") -> dict:
        """
        단순화된 스윙 신호 반환 (대시보드용)
        """
        result = self.full_analysis(ticker, period)
        if 'error' in result:
            return result
        
        return {
            'ticker': result['ticker'],
            'price': result['current_price'],
            'signal': result['swing_signal'],
            'confidence': result['confidence'],
            'rsi': result['rsi']['value'],
            'macd_hist': result['macd']['histogram'],
            'bb_pct_b': result['bollinger']['pct_b'],
            'trend': result['ma_cross']['current_trend'],
            'stop_loss': result['risk_management']['stop_loss'],
            'target': result['risk_management']['target'],
            'rr_ratio': result['risk_management']['risk_reward_ratio'],
        }


if __name__ == "__main__":
    analyzer = SwingTradingAnalyzer()
    
    print("[1] 애플 종합 기술적 분석...")
    result = analyzer.full_analysis("AAPL")
    print(f"    현재가: ${result['current_price']}")
    print(f"    RSI: {result['rsi']['value']} → {result['rsi']['signal']}")
    print(f"    MACD 히스토그램: {result['macd']['histogram']}")
    print(f"    볼린저 %B: {result['bollinger']['pct_b']}")
    print(f"    추세: {result['ma_cross']['current_trend']}")
    print(f"    🎯 최종 신호: {result['swing_signal']} (신뢰도: {result['confidence']*100:.0f}%)")
    print(f"    손절가: ${result['risk_management']['stop_loss']} | 목표가: ${result['risk_management']['target']}")
