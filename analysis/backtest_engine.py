"""
Backtest Engine
===============
- Role: Simulate trading strategies on historical data to calculate performance metrics.
- Metrics: Total Return, Win Rate, MDD, Sharpe Ratio, EV Validation.
- Target: Validate TechnicalSwingAnalyzer strategies.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from analysis.tech_swing_analyzer import TechnicalSwingAnalyzer
from analysis.macro_cycles import MacroCycleAnalyzer

class BacktestEngine:
    def __init__(
        self, 
        initial_capital: float = 10000.0,
        base_slippage: float = 0.0005, # 0.05% (기본값)
        commission: float = 0.00015,   # 0.015%
        tax_rate: float = 0.0025,      # 0.25%
        reinvest: bool = True,
        max_volume_pct: float = 0.1    # 일평균 거래량의 10% 이상 체결 제한
    ):
        self.initial_capital = initial_capital
        self.base_slippage = base_slippage
        self.commission = commission
        self.tax_rate = tax_rate
        self.reinvest = reinvest
        self.max_volume_pct = max_volume_pct
        
        self.analyzer = TechnicalSwingAnalyzer(paper_trading=True)
        self.macro_analyzer = MacroCycleAnalyzer()
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("BacktestEngine")

    def _calc_dynamic_slippage(self, price: float, volume: float, amount: float) -> float:
        """
        거래량과 거래금액에 따른 가변 슬리피지 계산
        - 거래량이 적을수록, 내 주문이 비중이 높을수록 슬리피지 증가
        """
        if volume <= 0: return self.base_slippage
        
        # 내 주문이 전일 거래량에서 차지하는 비중 (Impact Ratio)
        impact = (amount / volume) * 100 
        
        # 기본 슬리피지에 임팩트 비용(비선형) 추가
        # 예: 비중 1%당 0.1%p 슬리피지 증가
        dynamic_slippage = self.base_slippage + (impact * 0.001)
        return dynamic_slippage

    def _calc_entry_cost(self, effective_price: float, amount: float) -> float:
        """진입 시 수수료 계산"""
        return effective_price * self.commission * amount

    def _calc_exit_cost(self, effective_price: float, amount: float) -> float:
        """청산 시 수수료 + 세금 계산"""
        comm_cost = effective_price * self.commission * amount
        tax_cost = effective_price * self.tax_rate * amount
        return comm_cost + tax_cost

    def run_backtest(self, ticker: str, interval: str = "1h", period: str = "1y") -> dict:
        """특정 티커에 대해 과거 데이터를 기반으로 전략 시뮬레이션 수행"""
        self.logger.info(f"Starting backtest for {ticker} ({interval}, {period})...")
        
        # 1. 데이터 수집
        df = self.analyzer.fetch_yahoo_data(ticker, interval=interval, period=period)
        if df.empty or len(df) < 100:
            self.logger.warning(f"Insufficient data for backtest: {ticker}")
            return {"error": "Insufficient data"}
            
        # 2. 지표 계산
        df = self.analyzer.get_indicators(df)
        df['ema_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # 2b. 시장 지수(SPY) 데이터 연동 (Regime Filter용)
        spy_df = self.analyzer.fetch_yahoo_data("SPY", interval=interval, period=period)
        if not spy_df.empty:
            spy_df['spy_sma_200'] = spy_df['Close'].rolling(window=200).mean()
            # df와 spy_df 인덱스 동기화 (reindex)
            df['spy_close'] = spy_df['Close'].reindex(df.index, method='ffill')
            df['spy_sma_200'] = spy_df['spy_sma_200'].reindex(df.index, method='ffill')
        else:
            df['spy_sma_200'] = np.nan
        
        # 3. 시뮬레이션 변수
        capital = self.initial_capital
        position = 0
        entry_price = 0
        trades = []
        
        # 4. 루프 순회 (벡터화 대신 가독성을 위해 순차 순회)
        for i in range(20, len(df)):
            # [CRITICAL] Look-ahead Bias 차단: T 시계열의 데이터만 사용
            # 현재(i) 시점의 Close를 보려면, 매매 결정은 i-1 시점까지의 데이터(지표)에 근거해야 함
            curr = df.iloc[i]
            prev = df.iloc[i-1] # 결정 근거
            
            # 실제 체결가 결정 (슬리피지 반영)
            # 여기서는 i 시점의 시가(Open) 또는 평균(High+Low)/2를 사용하는 것이 더 정교함(사용자 요청 반영)
            execution_price = (curr['High'] + curr['Low']) / 2
            
            # 매수 로직 (TechnicalSwingAnalyzer 로직 이식 + SPY 필터)
            if position == 0:
                is_buy = False
                # 시장 필터: T-1 시점의 데이터로 결정
                market_is_good = pd.isna(prev.get('spy_sma_200')) or prev['spy_close'] > prev['spy_sma_200']
                
                if market_is_good:
                    # T-1 시점의 지표를 기준으로 진입 판단
                    is_bull_trend = prev['Close'] > prev['ema_200']
                    
                    # Setup 1: Wave Ride (불마켓 눌림목)
                    if is_bull_trend and prev['Close'] <= prev['bb_lower'] and prev['rsi'] < 40:
                        is_buy = True
                    # Setup 2: Trend Following
                    elif (prev['macd'] > prev['macd_signal'] and df.iloc[i-2]['macd'] <= df.iloc[i-2]['macd_signal'] 
                          and is_bull_trend and prev['rsi'] < 60):
                        is_buy = True
                    
                if is_buy:
                    # 거래량 기반 체결 가능성 검토 (T-1 거래량의 일정 수준 이하만)
                    max_sharable_amount = prev['Volume'] * self.max_volume_pct
                    
                    # 1. 가변 슬리피지 계산
                    # 진입 수량 예측 (러프하게 자본금/가격)
                    estimated_amount = capital / execution_price
                    actual_slippage = self._calc_dynamic_slippage(execution_price, prev['Volume'], estimated_amount)
                    
                    effective_entry_price = execution_price * (1 + actual_slippage)
                    
                    # 실질 수량 (수수료 포함)
                    buyable_position = capital / (effective_entry_price * (1 + self.commission))
                    
                    # 체결 제한 적용
                    position = min(buyable_position, max_sharable_amount)
                    capital -= position * effective_entry_price * (1 + self.commission)
                    
                    entry_price = execution_price
                    atr = prev['atr']
                    # 익절은 무제한(TS), 초기 손절은 ATR 2배
                    tp = entry_price * 2.0 
                    sl = entry_price - (atr * 2.0)
                    highest_price = entry_price 
                    trades.append({
                        "entry_date": df.index[i],
                        "entry_price": entry_price,
                        "tp": tp,
                        "sl": sl,
                        "type": "BUY",
                        "partial_exit": False
                    })
            
            # 매도 로직
            elif position > 0:
                trade = trades[-1]
                is_exit = False
                exit_reason = ""
                
                # T-1 시점까지의 최고가 기반 TS 업데이트 (Look-ahead 방지)
                if prev['Close'] > highest_price:
                    highest_price = prev['Close']
                    profit_at_prev = (highest_price / entry_price - 1) * 100
                    
                    if profit_at_prev > 10.0: mult = 6.0
                    elif profit_at_prev > 3.0: mult = 3.0
                    else: mult = 1.5
                        
                    new_sl = highest_price - (prev['atr'] * mult)
                    trade['sl'] = max(trade['sl'], new_sl)
                
                # 실시간 가격(i 시점) 모니터링
                current_price = execution_price
                profit_pct = (current_price / entry_price - 1) * 100
                
                # 분할 익절 로직
                if not trade['partial_exit'] and profit_pct >= 5.0:
                    actual_slippage = self._calc_dynamic_slippage(current_price, prev['Volume'], position * 0.5)
                    effective_exit_price = current_price * (1 - actual_slippage)
                    
                    exit_revenue = (position * 0.5) * effective_exit_price
                    exit_cost = self._calc_exit_cost(effective_exit_price, position * 0.5)
                    
                    capital += (exit_revenue - exit_cost)
                    position *= 0.5
                    trade['partial_exit'] = True
                
                # 청산 조건 체크
                if current_price >= trade['tp']:
                    is_exit = True
                    exit_reason = "TP"
                elif current_price <= trade['sl']:
                    is_exit = True
                    exit_reason = "SL/TS"
                    
                if is_exit:
                    actual_slippage = self._calc_dynamic_slippage(current_price, prev['Volume'], position)
                    effective_exit_price = current_price * (1 - actual_slippage)
                    
                    exit_revenue = position * effective_exit_price
                    exit_cost = self._calc_exit_cost(effective_exit_price, position)
                    capital += (exit_revenue - exit_cost)
                    
                    trade.update({
                        "exit_date": df.index[i],
                        "exit_price": current_price,
                        "profit_pct": (capital / self.initial_capital - 1) * 100 if not self.reinvest else 0, # 단순화
                        "reason": exit_reason
                    })
                    position = 0
                    entry_price = 0
                    
                    # 복리 재투자 여부에 따른 조정 (reinvest=False면 수익금을 별도 계좌로 뺌)
                    if not self.reinvest:
                        # 여기서는 단순화를 위해 reinvest=True가 기본이며, False일 경우의 로직은 필요시 고도화
                        pass

        # 5. 결과 집계
        if not trades:
            return {"ticker": ticker, "total_return_pct": 0, "win_rate": 0, "trade_count": 0}
            
        # 완료되지 않은 거래 제외
        completed_trades = [t for t in trades if "exit_price" in t]
        if not completed_trades:
            return {"ticker": ticker, "total_return_pct": 0, "win_rate": 0, "trade_count": 0}

        profits = [t['profit_pct'] for t in completed_trades]
        win_rate = len([p for p in profits if p > 0]) / len(profits) * 100
        total_return = (capital / self.initial_capital - 1) * 100
        
        # MDD 계산
        equity_curve = [self.initial_capital]
        temp_cap = self.initial_capital
        for p in profits:
            temp_cap *= (1 + p/100)
            equity_curve.append(temp_cap)
        
        equity_series = pd.Series(equity_curve)
        drawdown = (equity_series.cummax() - equity_series) / equity_series.cummax() * 100
        mdd = drawdown.max()

        # 6. 벤치마크 (Buy & Hold) 계산
        start_price = df.iloc[20]['Close']
        end_price = df.iloc[-1]['Close']
        benchmark_return_pct = (end_price / start_price - 1) * 100

        return {
            "ticker": ticker,
            "total_return_pct": round(total_return, 2),
            "benchmark_return_pct": round(benchmark_return_pct, 2),
            "alpha": round(total_return - benchmark_return_pct, 2),
            "win_rate": round(win_rate, 2),
            "mdd": round(mdd, 2),
            "trade_count": len(completed_trades)
        }

    def run_hyper_alpha_rotation_backtest(self, tickers: list[str], interval: str = "1h", period: str = "1y") -> dict:
        """
        Hyper-Alpha Wave-Rider 전략 구동 (로테이션 + 무제한 익절)
        """
        self.logger.info(f"Starting Hyper-Alpha Rotation backtest for {tickers}...")
        
        # 1. 모든 티커 데이터 로드 및 지표 계산
        asset_data = {}
        for t in tickers:
            df = self.analyzer.fetch_yahoo_data(t, interval=interval, period=period)
            df = self.analyzer.get_indicators(df)
            df['ema_200'] = df['Close'].ewm(span=200, adjust=False).mean()
            asset_data[t] = df
            
        spy_df = self.analyzer.fetch_yahoo_data("SPY", interval=interval, period=period)
        spy_df['sma_200'] = spy_df['Close'].rolling(window=200).mean()
        
        # 공통 타임라인 추출
        common_index = asset_data[tickers[0]].index
        for t in tickers[1:]:
            common_index = common_index.intersection(asset_data[t].index)
        
        capital = self.initial_capital
        position = 0
        current_ticker = None
        trades = []
        highest_price = 0
        
        for i in range(200, len(common_index)):
            dt = common_index[i]
            spy_curr = spy_df.loc[dt] if dt in spy_df.index else None
            market_is_good = spy_curr is None or spy_curr['Close'] > spy_curr['sma_200']
            
            if not market_is_good and position > 0:
                # 시장 급락 시 즉시 현금화
                price = asset_data[current_ticker].loc[dt, 'Close']
                capital = position * price
                trades[-1].update({"exit_date": dt, "exit_price": price, "reason": "MARKET_RISK"})
                position = 0
                current_ticker = None
                continue

            if position == 0 and market_is_good:
                # 1. 가장 강한 종목 찾기
                best_t = None
                max_roc = -999.0
                for t in tickers:
                    if asset_data[t].loc[dt, 'roc_14'] > max_roc:
                        max_roc = asset_data[t].loc[dt, 'roc_14']
                        best_t = t
                
                # 2. 진입 조건 체크 (장기 추세 위)
                curr_data = asset_data[best_t].loc[dt]
                if curr_data['Close'] > curr_data['ema_200'] and curr_data['rsi'] < 65:
                    current_ticker = best_t
                    price = curr_data['Close']
                    
                    effective_entry_price = price * (1 + self.slippage)
                    position = capital / (effective_entry_price * (1 + self.commission))
                    capital = 0
                    
                    highest_price = price
                    trades.append({
                        "ticker": current_ticker,
                        "entry_date": dt,
                        "entry_price": price,
                        "sl": price - (curr_data['atr'] * 3.5),
                        "tp": price * 10.0,
                        "type": "BUY",
                        "partial_exit": False
                    })
            
            elif position > 0:
                # 보유 중인 종목 관리
                curr_data = asset_data[current_ticker].loc[dt]
                price = curr_data['Close']
                trade = trades[-1]
                profit_pct = (price / trade['entry_price'] - 1) * 100
                
                # 최고가 갱신 및 3단계 동적 트레일링 스탑
                # [NEW] Cash-Flow 50% 분할 익절 로직 (Rotation에도 적용)
                if not trade['partial_exit'] and profit_pct >= 5.0:
                    effective_exit_price = price * (1 - self.slippage)
                    exit_revenue = (position * 0.5) * effective_exit_price
                    exit_cost = self._calc_exit_cost(effective_exit_price, position * 0.5)
                    capital += (exit_revenue - exit_cost)
                    position *= 0.5
                    trade['partial_exit'] = True
                    self.logger.info(f"[{current_ticker}] Partial Exit at {price} ({profit_pct:.2f}%)")

                # 손절 또는 TS 이탈
                if price <= trade['sl']:
                    effective_exit_price = price * (1 - self.slippage)
                    exit_revenue = position * effective_exit_price
                    exit_cost = self._calc_exit_cost(effective_exit_price, position)
                    capital += (exit_revenue - exit_cost)
                    
                    trade.update({"exit_date": dt, "exit_price": price, "reason": "SL/TS"})
                    position = 0
                    current_ticker = None
                    continue
                
                # 순환매(Rotation) 로직: 현재 종목보다 5% 이상 강한 종목 발견 시 교체
                best_t = None
                max_roc = -999.0
                for t in tickers:
                    if asset_data[t].loc[dt, 'roc_14'] > max_roc:
                        max_roc = asset_data[t].loc[dt, 'roc_14']
                        best_t = t
                
                current_roc = curr_data['roc_14']
                if best_t != current_ticker and (max_roc - current_roc) > 7.0:
                    # 교체 단행 (기존 종목 매도 + 새 종목 매수)
                    effective_exit_price = price * (1 - self.slippage)
                    exit_revenue = position * effective_exit_price
                    exit_cost = self._calc_exit_cost(effective_exit_price, position)
                    capital += (exit_revenue - exit_cost)
                    
                    trade.update({"exit_date": dt, "exit_price": price, "reason": "ROTATION"})
                    
                    # 즉시 새 종목 진입
                    new_curr = asset_data[best_t].loc[dt]
                    current_ticker = best_t
                    new_price = new_curr['Close']
                    
                    effective_entry_price = new_price * (1 + self.slippage)
                    position = capital / (effective_entry_price * (1 + self.commission))
                    capital = 0
                    
                    highest_price = new_price
                    trades.append({
                        "ticker": current_ticker,
                        "entry_date": dt,
                        "entry_price": new_price,
                        "sl": new_price - (new_curr['atr'] * 2.5),
                        "tp": new_price * 10.0,
                        "type": "BUY",
                        "partial_exit": False
                    })

        # 결과 계산
        final_value = capital if position == 0 else position * asset_data[current_ticker].iloc[-1]['Close']
        total_return = (final_value / self.initial_capital - 1) * 100
        
        return {
            "strategy": "Hyper-Alpha Rotation",
            "total_return_pct": total_return,
            "trade_count": len(trades)
        }

    def run_frequency_contest(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """동일 종목에 대해 다양한 타임프레임의 성과를 비교 (데이터 가용성 고려)"""
        self.logger.info(f"Running Frequency Contest for {ticker}...")
        
        # Yahoo Finance API 제한: 15m은 최근 60일까지만 가능
        intervals_config = [
            {"interval": "15m", "period": "60d"},
            {"interval": "1h", "period": "1y"},
            {"interval": "1d", "period": "max"}
        ]
        results = []
        
        for cfg in intervals_config:
            interval = cfg["interval"]
            p = cfg["period"]
            res = self.run_backtest(ticker, interval=interval, period=p)
            
            if "error" in res:
                self.logger.warning(f"Failed to get results for {interval}: {res['error']}")
                continue
                
            results.append({
                "Interval": interval,
                "Period": p,
                "Return (%)": res.get("total_return_pct", 0),
                "Benchmark (%)": res.get("benchmark_return_pct", 0),
                "Trade Count": res.get("trade_count", 0),
                "Win Rate (%)": res.get("win_rate", 0),
                "MDD (%)": res.get("mdd", 0)
            })
            
        return pd.DataFrame(results)

if __name__ == "__main__":
    engine = BacktestEngine(initial_capital=10000.0, reinvest=True)
    
    ticker = "TQQQ"
    print(f"\n[CONTEST] {ticker} Frequency & Cost Analytics")
    df_contest = engine.run_frequency_contest(ticker, period="1y")
    print(df_contest.to_string(index=False))
    
    print("\n[STEP 2] Hyper-Alpha 로테이션 테스트 (TQQQ, SOXL, FNGU) + 거래 비용 반영")
    res2 = engine.run_hyper_alpha_rotation_backtest(["TQQQ", "SOXL", "FNGU"], interval="1h", period="1y")
    print(f"Outcome (with costs): {res2['total_return_pct']:.2f}% (Trade Count: {res2['trade_count']})")
