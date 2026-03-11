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
        slippage: float = 0.0005, # 0.05% (현실적 수치로 조정)
        commission: float = 0.00015, # 0.015%
        tax_rate: float = 0.0025, # 0.25%
        reinvest: bool = True
    ):
        self.initial_capital = initial_capital
        self.slippage = slippage
        self.commission = commission
        self.tax_rate = tax_rate
        self.reinvest = reinvest
        
        self.analyzer = TechnicalSwingAnalyzer(paper_trading=True)
        self.macro_analyzer = MacroCycleAnalyzer()
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("BacktestEngine")

    def _calc_entry_cost(self, effective_price: float, amount: float) -> float:
        """진입 시 수수료 계산 (슬리피지는 이미 가격에 반영됨)"""
        return effective_price * self.commission * amount

    def _calc_exit_cost(self, effective_price: float, amount: float) -> float:
        """청산 시 수수료 + 세금 계산 (슬리피지는 이미 가격에 반영됨)"""
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
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            price = curr['Close']
            
            # 매수 로직 (TechnicalSwingAnalyzer 로직 이식 + SPY 필터)
            if position == 0:
                is_buy = False
                # 시장 필터: SPY가 200 SMA 위에 있을 때만 (단기 반등 제외, 안정적 추세 지향)
                market_is_good = pd.isna(curr.get('spy_sma_200')) or curr['spy_close'] > curr['spy_sma_200']
                
                if market_is_good:
                    # 강세장 판정: 가격이 장기 이평선(EMA 200) 위에 있을 때
                    is_bull_trend = price > curr['ema_200']
                    
                    # Setup 1: Wave Ride (불마켓 눌림목)
                    if is_bull_trend and price <= curr['bb_lower'] and curr['rsi'] < 40: # RSI 필터 강화 (45->40)
                        is_buy = True
                    # Setup 2: Trend Following
                    elif (curr['macd'] > curr['macd_signal'] and prev['macd'] <= prev['macd_signal'] and is_bull_trend and curr['rsi'] < 60):
                        is_buy = True
                    
                if is_buy:
                    # 1. 슬리피지가 반영된 실질 진입가 계산
                    effective_entry_price = price * (1 + self.slippage)
                    # 2. 수수료를 제외하고 살 수 있는 최대 수량 계산
                    # capital = (effective_entry_price * position) + (effective_entry_price * position * commission)
                    # capital = effective_entry_price * position * (1 + commission)
                    position = capital / (effective_entry_price * (1 + self.commission))
                    capital = 0 # 전량 매수
                    
                    entry_price = price
                    atr = curr['atr']
                    # 익절은 무제한(TS), 초기 손절은 ATR 2배로 널널하게
                    tp = price * 2.0 
                    sl = price - (atr * 2.0)
                    highest_price = price 
                    trades.append({
                        "entry_date": df.index[i],
                        "entry_price": entry_price,
                        "tp": tp,
                        "sl": sl,
                        "type": "BUY",
                        "partial_exit": False # Cash-Flow 50% 익절 여부
                    })
            
            # 매도 로직 (익절/손절 + 확장형 트레일링 스탑)
            elif position > 0:
                trade = trades[-1]
                is_exit = False
                exit_reason = ""
                
                profit_pct = (price / entry_price - 1) * 100
                
                # 최고가 갱신 및 확장형 트레일링 스탑 업데이트
                if price > highest_price:
                    highest_price = price
                    # 메가 추세를 타기 위해 수익권에 진입(10% 이상)하면 TS를 ATR 6배로 대폭 확대
                    if profit_pct > 10.0:
                        mult = 6.0
                    elif profit_pct > 3.0:
                        mult = 3.0
                    else:
                        mult = 1.5
                        
                    new_sl = highest_price - (curr['atr'] * mult)
                    trade['sl'] = max(trade['sl'], new_sl)
                
                # [NEW] Cash-Flow 50% 분할 익절 로직
                if not trade['partial_exit'] and profit_pct >= 5.0:
                    effective_exit_price = price * (1 - self.slippage)
                    exit_revenue = (position * 0.5) * effective_exit_price
                    exit_cost = self._calc_exit_cost(effective_exit_price, position * 0.5)
                    
                    plus_flow = exit_revenue - exit_cost
                    capital += plus_flow
                    position *= 0.5
                    trade['partial_exit'] = True
                    self.logger.info(f"Partial Exit (50%) at {price} ({profit_pct:.2f}%) -> Cash: {plus_flow:.2f}")
                
                # 강제 익절 (파동의 끝이라고 판단될 때)
                if price >= trade['tp']:
                    is_exit = True
                    exit_reason = "TP"
                # 손절 또는 트레일링 스탑 이탈
                elif price <= trade['sl']:
                    is_exit = True
                    exit_reason = "SL/TS"
                    
                if is_exit:
                    effective_exit_price = price * (1 - self.slippage)
                    exit_revenue = position * effective_exit_price
                    exit_cost = self._calc_exit_cost(effective_exit_price, position)
                    capital += (exit_revenue - exit_cost)
                    
                    trade.update({
                        "exit_date": df.index[i],
                        "exit_price": price,
                        "profit_pct": (capital / (position * entry_price) - 1) * 100 if position > 0 else 0,
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
