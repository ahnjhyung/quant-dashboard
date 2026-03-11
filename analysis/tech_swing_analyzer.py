import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from typing import Optional
import logging
import time
from analysis.macro_cycles import MacroCycleAnalyzer

class TechnicalSwingAnalyzer:
    def __init__(self, paper_trading: bool = True):
        self.paper_trading = paper_trading
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("TechnicalSwingAnalyzer")
        self.macro_analyzer = MacroCycleAnalyzer()

    def fetch_yahoo_data(self, ticker: str, interval: str = "1d", period: str = "3mo") -> pd.DataFrame:
        """Yahoo Finance v8 API 직접 호출 (yfinance 라이브러리 우회)"""
        try:
            # period를 초 단위로 변환
            end_dt = datetime.now()
            if period == "3mo": start_dt = end_dt - timedelta(days=90)
            elif period == "6mo": start_dt = end_dt - timedelta(days=180)
            elif period == "1mo": start_dt = end_dt - timedelta(days=30)
            else: start_dt = end_dt - timedelta(days=365)
            
            p1 = int(start_dt.timestamp())
            p2 = int(end_dt.timestamp())
            
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={p1}&period2={p2}&interval={interval}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            res = requests.get(url, headers=headers)
            json_data = res.json()
            
            if not json_data['chart']['result']:
                return pd.DataFrame()
                
            result = json_data['chart']['result'][0]
            timestamps = result['timestamp']
            quote = result['indicators']['quote'][0]
            
            df = pd.DataFrame({
                'Open': quote['open'],
                'High': quote['high'],
                'Low': quote['low'],
                'Close': quote['close'],
                'Volume': quote['volume']
            }, index=[datetime.fromtimestamp(ts) for ts in timestamps])
            
            return df.dropna()
        except Exception as e:
            self.logger.error(f"Failed to fetch {ticker} via Direct API: {e}")
            return pd.DataFrame()

    def get_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """지표 계산: BB, RSI, MACD, ATR, EMA"""
        # Close price series
        close = df['Close']
        
        # 1. BB (Bollinger Bands)
        sma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        df['bb_upper'] = sma20 + (std20 * 2)
        df['bb_lower'] = sma20 - (std20 * 2)
        df['bb_mid'] = sma20
        
        # 2. RSI (Relative Strength Index)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 3. MACD
        exp12 = close.ewm(span=12, adjust=False).mean()
        exp26 = close.ewm(span=26, adjust=False).mean()
        df['macd'] = exp12 - exp26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        
        # 4. ATR (Average True Range)
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(14).mean()
        
        # 5. EMA 10, 20, 50
        df['ema_10'] = close.ewm(span=10, adjust=False).mean()
        df['ema_20'] = close.ewm(span=20, adjust=False).mean()
        df['ema_50'] = close.ewm(span=50, adjust=False).mean()
        
        # 6. Bollinger %B (Price relative to bands)
        df['bb_pct_b'] = (close - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        
        # 8. ROC (Rate of Change) for Relative Strength
        df['roc_14'] = close.pct_change(periods=14) * 100
        
        return df

    def get_relative_strength(self, ticker_df: pd.DataFrame, spy_df: pd.DataFrame) -> bool:
        """시장 지수(SPY) 대비 상대 강도 판정 (주도주 여부)"""
        if spy_df.empty or ticker_df.empty:
            return True
        
        ticker_roc = ticker_df['roc_14'].iloc[-1]
        spy_roc = (spy_df['Close'].iloc[-1] / spy_df['Close'].iloc[-14] - 1) * 100 if len(spy_df) >= 14 else 0
        
        return ticker_roc > spy_roc

    def get_best_momentum_ticker(self, tickers: list[str], interval: str = "1h", period: str = "1mo") -> Optional[str]:
        """주어진 종목 리스트 중 14일 ROC가 가장 높은(가장 강한) 종목 반환"""
        best_ticker = None
        max_roc = -999.0
        
        for ticker in tickers:
            df = self.fetch_yahoo_data(ticker, interval=interval, period=period)
            if df.empty or len(df) < 14:
                continue
            df = self.get_indicators(df)
            curr_roc = df['roc_14'].iloc[-1]
            if curr_roc > max_roc:
                max_roc = curr_roc
                best_ticker = ticker
        
        return best_ticker

    def calculate_ev(self, ticker: str, current_price: float, atr: float, signal_type: str) -> dict:
        """
        단순화된 기대값 계산 (과거 통계 기반 추정)
        - Take Profit (TP): current_price + (atr * 1.5)
        - Stop Loss (SL): current_price - (atr * 0.75)
        - Win Rate: 전략별 기본 승률 (향후 백테스트 엔진과 연동 가능)
        """
        # 현실적인 승률 적용
        win_rate = 0.55 if signal_type == "Mean Reversion" else 0.52
        
        # 손익비(RR) 조정 (백테스트 최적화값)
        tp_dist = atr * 1.6
        sl_dist = atr * 0.8
        
        # EV = (P_win * TP) - (P_loss * SL)
        ev_val = (win_rate * tp_dist) - ((1 - win_rate) * sl_dist)
        ev_pct = (ev_val / current_price) * 100
        
        return {
            "ev_value": round(ev_val, 2),
            "ev_pct": round(ev_pct, 2),
            "win_rate": win_rate,
            "tp_price": round(current_price + tp_dist, 2),
            "sl_price": round(current_price - sl_dist, 2),
            "risk_reward": round(tp_dist / sl_dist, 2)
        }

    def analyze_ticker(self, ticker: str, interval: str = "1d", period: str = "3mo") -> dict:
        """특정 티커에 대한 기술적 분석 수행 및 신호 생성"""
        try:
            # Direct API 호출
            df = self.fetch_yahoo_data(ticker, interval=interval, period=period)
            
            if df.empty or len(df) < 30:
                self.logger.warning(f"Insufficient data for {ticker}")
                return None
            
            df = self.get_indicators(df)
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            curr_price = float(last['Close'])
            # 3. 매크로 국면 및 시장 정보 연동
            regime = self.macro_analyzer.get_current_regime()
            spy_df = self.fetch_yahoo_data("SPY", interval=interval, period=period)
            is_leader = self.get_relative_strength(df, spy_df)
            
            # 국면별 파라미터 조정
            ts_mult = 3.5 if regime['cycle_state'] == "GOLDILOCKS" else 1.5
            entry_rsi = 40 if regime['cycle_state'] == "GOLDILOCKS" else 25
            
            signals = []
            
            # Setup 1: Wave Ride (상슬 파도의 눌림목 포착)
            # 조건: 시장 주도주 + RSI 40(또는 25) 이하 과매도 + 이평선 지지
            if (is_leader and rsi < entry_rsi and curr_price > last['ema_50']):
                ev_data = self.calculate_ev(ticker, curr_price, atr, "Wave Ride")
                # 트레일링 스탑 정보 추가
                ev_data['ts_atr_mult'] = ts_mult
                signals.append({
                    "strategy": f"Wave Rider (Pullback) - {regime['cycle_state']}",
                    "reason": f"시장 주도주({ticker})의 추세 구간 내 눌림목 포착",
                    **ev_data
                })
                
            # Setup 2: Wave Breakout (상승 파도의 시작점 포착)
            # 조건: 전고점(BB 상단) 돌파 + 매크로 긍정 + 골든크로스
            if (last['macd'] > last['macd_signal'] and prev['macd'] <= prev['macd_signal'] and 
                curr_price >= last['bb_upper'] and regime['cycle_state'] == "GOLDILOCKS"):
                ev_data = self.calculate_ev(ticker, curr_price, atr, "Wave Breakout")
                ev_data['ts_atr_mult'] = ts_mult
                signals.append({
                    "strategy": f"Wave Rider (Breakout) - {regime['cycle_state']}",
                    "reason": "골디락스 국면 내 전고점 돌파 및 상승 파동 시작",
                    **ev_data
                })

            if not signals:
                return None
                
            return {
                "ticker": ticker,
                "price": round(curr_price, 2),
                "signals": signals,
                "interval": interval,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing {ticker}: {e}")
            return None

    def run_multi_analysis(self, tickers: list, interval: str = "1d") -> list:
        """여러 티커에 대한 일괄 분석 (스윙 & 데이 병행)"""
        results = []
        for t in tickers:
            # 1. 스윙 분석 (일봉)
            res_swing = self.analyze_ticker(t, interval="1d", period="6mo")
            if res_swing:
                results.append(res_swing)
            
            # 2. 데이트레이딩 분석 (1시간 봉)
            res_day = self.analyze_ticker(t, interval="1h", period="1mo")
            if res_day:
                results.append(res_day)
                
        return results

if __name__ == "__main__":
    analyzer = TechnicalSwingAnalyzer()
    # 데모용 주요 티커 분석
    test_tickers = ["TQQQ", "SOXX", "BTC-USD", "NVDA", "005930.KS"]
    reports = analyzer.run_multi_analysis(test_tickers)
    for r in reports:
        print(f"\n[Stock: {r['ticker']}] Price: {r['price']}")
        for s in r['signals']:
            print(f" - {s['strategy']}: {s['reason']}")
            print(f"   EV: {s['ev_pct']}% | TP: {s['tp_price']} | SL: {s['sl_price']}")
