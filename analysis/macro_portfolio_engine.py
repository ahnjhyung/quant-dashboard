"""
Macro Portfolio Engine
======================
- Role: Perform long-term historical backtesting for multi-asset portfolios.
- Objective: Compare different asset allocation strategies over various market regimes.
- Metrics: CAGR, Sharpe Ratio, Sortino Ratio, MDD, Rolling Returns, Correlation.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from data_collectors.supabase_manager import SupabaseManager
from data_collectors.yf_utils import download_ticker_data

class MacroPortfolioEngine:
    def __init__(self, initial_capital: float = 10000.0, commission: float = 0.0001):
        self.initial_capital = initial_capital
        self.commission = commission
        self.logger = logging.getLogger("MacroPortfolioEngine")
        self.db = SupabaseManager()
        
        # Long-term Proxy Mapping (ETF -> Older Mutual Fund or Index)
        self.proxy_map = {
            "SPY": "VFINX",   # S&P 500 (since 1976)
            "TLT": "VUSTX",   # Long Term Treasury (since 1986)
            "IEF": "VFITX",   # Interm Term Treasury (since 1991)
            "GLD": "GC=F",     # Gold (since 1970s)
            "GSG": "CL=F",     # Commodities Proxy (Crude Oil)
            "QQQ": "VFINX",   # Tech proxy (older era use S&P)
            "IWM": "NAESX",   # Small Cap (since 1960s)
        }

    def fetch_long_data(self, tickers: List[str], start_date: str = "1970-01-01") -> pd.DataFrame:
        """Fetch and merge historical data for given tickers, using proxies where necessary."""
        all_data = pd.DataFrame()
        
        for t in tickers:
            try:
                # 1. Fetch Primary Ticker (Using robust utility)
                df = download_ticker_data(t, start=start_date)
                
                if df.empty or df.index[0] > pd.to_datetime(start_date) + timedelta(days=365):
                    # 2. Try Proxy if primary is too short
                    proxy = self.proxy_map.get(t)
                    if proxy:
                        self.logger.info(f"Primary {t} insufficient. Fetching proxy {proxy}...")
                        proxy_df = download_ticker_data(proxy, start=start_date)
                        if not proxy_df.empty:
                            # Merge logic: Use primary where available, else proxy (scaled)
                            if not df.empty:
                                common_date = df.index[0]
                                ratio = df.loc[common_date, 'Close'] / proxy_df.loc[common_date, 'Close']
                                if isinstance(ratio, pd.Series): ratio = ratio.iloc[0]
                                scaled_proxy = proxy_df.loc[:common_date]['Close'] * ratio
                                df = pd.concat([scaled_proxy[:-1], df['Close']], axis=0)
                            else:
                                df = proxy_df['Close']
                
                if df is None or df.empty:
                    self.logger.warning(f"Could not fetch data for {t} nor its proxy.")
                    continue
                
                # Normalize column name
                if isinstance(df, pd.DataFrame):
                    if 'Close' in df.columns:
                        df = df['Close']
                    else:
                        # Sometimes yfinance returns column with ticker name
                        df = df.iloc[:, 0]
                
                series = df.rename(t)
                if all_data.empty:
                    all_data = pd.DataFrame(series)
                else:
                    all_data = all_data.join(series, how='outer')
            except Exception as e:
                self.logger.error(f"Error fetching {t}: {e}")
                
        # Forward fill and drop leading NaNs for the backtest start
        return all_data.ffill()

    def run_backtest(
        self, 
        portfolio_weights: Dict[str, float], 
        data: pd.DataFrame, 
        rebalance_freq: str = "ME"
    ) -> Dict:
        """Run a backtest for a single portfolio configuration."""
        # Filter data to columns that actually exist
        available_tickers = [t for t in portfolio_weights.keys() if t in data.columns]
        if not available_tickers:
            return {"error": f"None of the tickers {list(portfolio_weights.keys())} found in downloaded data."}
            
        valid_data = data[available_tickers].dropna()
        if valid_data.empty:
            return {"error": "No overlapping data for these assets."}
            
        returns = valid_data.pct_change().dropna()
        rebalance_dates = pd.date_range(start=returns.index[0], end=returns.index[-1], freq=rebalance_freq)
        
        capital = self.initial_capital
        history = []
        # Extract weights only for available tickers and normalize them to sum to 1
        raw_weights = np.array([portfolio_weights[t] for t in available_tickers])
        current_weights = raw_weights / raw_weights.sum() if raw_weights.sum() > 0 else raw_weights
        
        # Initialize
        shares = (capital * current_weights) / valid_data.loc[returns.index[0]]
        
        for dt in returns.index:
            prices = valid_data.loc[dt]
            total_value = (shares * prices).sum()
            
            if dt in rebalance_dates:
                # Rebalance
                target_value = total_value
                # Simple commission on the churn (not optimized but representative)
                # target_shares = (target_value * current_weights) / prices
                # Fix: more accurate rebalancing tracking isn't needed for high-level macro
                shares = (target_value * current_weights) / prices
                total_value -= total_value * self.commission # cost on total rebalance
            
            history.append({"date": dt, "total_value": total_value})
            
        df_hist = pd.DataFrame(history).set_index("date")
        
        # Calculate Metrics
        final_v = df_hist['total_value'].iloc[-1]
        total_ret = (final_v / self.initial_capital - 1)
        years = (df_hist.index[-1] - df_hist.index[0]).days / 365.25
        cagr = (final_v / self.initial_capital)**(1/years) - 1 if years > 0 else 0
        
        daily_returns = df_hist['total_value'].pct_change().dropna()
        vol = daily_returns.std() * np.sqrt(252)
        
        # Standard Sharpe: annualized arithmetic mean excess return / annualized vol
        annual_mean_return = daily_returns.mean() * 252
        rf = 0.02  # Risk-free rate
        sharpe = (annual_mean_return - rf) / vol if vol > 0 else 0
        
        # Sortino: uses downside deviation instead of total vol
        neg_returns = daily_returns[daily_returns < 0]
        downside_vol = neg_returns.std() * np.sqrt(252)
        sortino = (annual_mean_return - rf) / downside_vol if downside_vol > 0 else 0
        
        mdd = ((df_hist['total_value'] - df_hist['total_value'].cummax()) / df_hist['total_value'].cummax()).min()
        calmar = cagr / abs(mdd) if mdd != 0 else 0
        
        # Monthly Returns Matrix
        monthly_ret = df_hist['total_value'].resample('ME').last().pct_change().dropna()
        monthly_matrix = monthly_ret.to_frame()
        monthly_matrix['year'] = monthly_matrix.index.year
        monthly_matrix['month'] = monthly_matrix.index.month
        monthly_matrix = monthly_matrix.pivot(index='year', columns='month', values='total_value')

        return {
            "final_value": final_v,
            "total_return": total_ret,
            "cagr": cagr,
            "volatility": vol,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "max_drawdown": mdd,
            "history": df_hist,
            "monthly_matrix": monthly_matrix
        }

    def compare_portfolios(
        self, 
        portfolios: Dict[str, Dict[str, float]], 
        start_date: str = "1990-01-01",
        rebalance_freq: str = "ME"
    ) -> Dict:
        """Compare multiple portfolios side by side.
        
        Args:
            portfolios: Dict of {name: {ticker: weight}} for each strategy.
            start_date: Backtest start date string (YYYY-MM-DD).
            rebalance_freq: Pandas frequency string for rebalancing (ME, QE, YE).
            
        Returns:
            Dict of {strategy_name: backtest_result_dict}.
        """
        # Get all unique tickers
        all_tickers = set()
        for p in portfolios.values():
            all_tickers.update(p.keys())

        data = self.fetch_long_data(list(all_tickers), start_date=start_date)
        
        # 공정한 비교를 위해 모든 티커의 데이터가 존재하는 시점부터 백테스트 시작
        data = data.dropna()
        
        results = {}
        
        for name, weights in portfolios.items():
            results[name] = self.run_backtest(weights, data, rebalance_freq=rebalance_freq)
            
        return results

    # ── Regime-based diversified allocation weights ─────────────────────
    # Each regime tilts toward favorable asset classes but maintains diversification.
    # Sum of weights per regime = 1.0
    REGIME_WEIGHTS = {
        "Goldilocks": {"SPY": 0.55, "TLT": 0.20, "GLD": 0.15, "GSG": 0.10},
        "Reflation":  {"SPY": 0.35, "TLT": 0.10, "GLD": 0.20, "GSG": 0.35},
        "Stagflation": {"SPY": 0.10, "TLT": 0.15, "GLD": 0.50, "GSG": 0.25},
        "Deflation":  {"SPY": 0.15, "TLT": 0.55, "GLD": 0.20, "GSG": 0.10},
    }

    def _classify_regime(self, g_trend: bool, i_trend: bool) -> str:
        """Classify economic regime from growth/inflation trend signals.
        
        Args:
            g_trend: True if growth above rolling mean.
            i_trend: True if inflation above rolling mean.
            
        Returns:
            Regime name string.
        """
        if g_trend and not i_trend:
            return "Goldilocks"
        elif g_trend and i_trend:
            return "Reflation"
        elif not g_trend and i_trend:
            return "Stagflation"
        else:
            return "Deflation"

    def run_dynamic_macro_backtest(
        self, 
        price_data: pd.DataFrame,
        rebalance_freq: str = "ME"
    ) -> Dict:
        """4-Quadrant Macro Model Backtest with diversified regime allocations.
        
        Instead of concentrating 100% in a single asset per regime, this method
        applies diversified tilts (REGIME_WEIGHTS) and rebalances at the user's
        chosen frequency.
        
        Args:
            price_data: DataFrame of daily prices (columns = ticker symbols).
            rebalance_freq: Pandas frequency string (ME, QE, YE).
            
        Returns:
            Dict with backtest metrics, history, and regime labels.
        """
        self.logger.info("Running Dynamic Macro Backtest (Diversified Quadrants)...")
        
        macro_assets = ["SPY", "TLT", "GLD", "GSG"]
        missing = [t for t in macro_assets if t not in price_data.columns]
        if missing:
            return {"error": f"Missing price data for macro assets: {missing}"}
        
        # 1. Get Macro Data from Supabase
        growth_df = self.db.get_macro_history("INDPRO", days=10000)
        inflation_df = self.db.get_macro_history("CPIAUCSL", days=10000)
        
        if growth_df is None or inflation_df is None or growth_df.empty or inflation_df.empty:
            return {"error": "Macro data (INDPRO/CPI) missing in Supabase. Run backfiller first."}

        # 2. Calculate ROC (Year-over-Year change)
        macro = pd.DataFrame(index=price_data.index)
        macro['growth_roc'] = growth_df['value'].pct_change(12).reindex(
            price_data.index, method='ffill'
        )
        macro['inflation_roc'] = inflation_df['value'].pct_change(12).reindex(
            price_data.index, method='ffill'
        )
        macro = macro.dropna()

        if macro.empty:
            return {"error": "Macro overlap data too short or missing. Need at least 60 days of history for indicators."}

        # 3. Trend signals: above or below 60-day rolling mean
        macro['g_trend'] = macro['growth_roc'] > macro['growth_roc'].rolling(60).mean()
        macro['i_trend'] = macro['inflation_roc'] > macro['inflation_roc'].rolling(60).mean()
        macro = macro.dropna()

        if macro.empty:
            return {"error": "Insufficient history for rolling indicators (Need > 60 days)."}

        # 4. Run simulation with diversified regime weights
        valid_idx = macro.index.intersection(price_data.index)
        if valid_idx.empty:
            return {"error": "No overlapping dates between price data and macro indicators."}

        history = []
        capital = self.initial_capital
        
        # Initial regime and allocation
        init_regime = self._classify_regime(
            macro.loc[valid_idx[0], 'g_trend'],
            macro.loc[valid_idx[0], 'i_trend']
        )
        init_weights = self.REGIME_WEIGHTS[init_regime]
        shares = {}
        for t in macro_assets:
            shares[t] = (capital * init_weights[t]) / price_data.loc[valid_idx[0], t]

        rebalance_dates = pd.date_range(
            start=valid_idx[0], end=valid_idx[-1], freq=rebalance_freq
        )

        for dt in valid_idx:
            prices = price_data.loc[dt]
            total_value = sum(shares[t] * prices[t] for t in macro_assets)
            
            regime = self._classify_regime(
                macro.loc[dt, 'g_trend'],
                macro.loc[dt, 'i_trend']
            )
            
            if dt in rebalance_dates:
                target_weights = self.REGIME_WEIGHTS[regime]
                for t in macro_assets:
                    shares[t] = (total_value * target_weights[t]) / prices[t]
                total_value -= total_value * self.commission

            history.append({"date": dt, "total_value": total_value, "regime": regime})

        df_hist = pd.DataFrame(history).set_index("date")
        
        if df_hist.empty or len(df_hist) < 2:
            return {"error": "Not enough data points to calculate metrics."}
        
        # Calculate Metrics
        final_v = df_hist['total_value'].iloc[-1]
        total_ret = (final_v / self.initial_capital - 1)
        years = (df_hist.index[-1] - df_hist.index[0]).days / 365.25
        cagr = (final_v / self.initial_capital)**(1/years) - 1 if years > 0 else 0
        
        daily_returns = df_hist['total_value'].pct_change().dropna()
        vol = daily_returns.std() * np.sqrt(252)
        
        annual_mean_return = daily_returns.mean() * 252
        rf = 0.02
        sharpe = (annual_mean_return - rf) / vol if vol > 0 else 0
        
        neg_returns = daily_returns[daily_returns < 0]
        downside_vol = neg_returns.std() * np.sqrt(252)
        sortino = (annual_mean_return - rf) / downside_vol if downside_vol > 0 else 0
        
        mdd = ((df_hist['total_value'] - df_hist['total_value'].cummax()) / df_hist['total_value'].cummax()).min()
        calmar = cagr / abs(mdd) if mdd != 0 else 0
        
        # Monthly Returns Matrix
        monthly_ret = df_hist['total_value'].resample('ME').last().pct_change().dropna()
        monthly_matrix = monthly_ret.to_frame()
        monthly_matrix['year'] = monthly_matrix.index.year
        monthly_matrix['month'] = monthly_matrix.index.month
        monthly_matrix = monthly_matrix.pivot(index='year', columns='month', values='total_value')
        
        return {
            "final_value": final_v,
            "total_return": total_ret,
            "cagr": cagr,
            "volatility": vol,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "max_drawdown": mdd,
            "history": df_hist,
            "regimes": df_hist['regime'],
            "monthly_matrix": monthly_matrix
        }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = MacroPortfolioEngine()
    
    ports = {
        "60/40": {"SPY": 0.6, "TLT": 0.4},
        "All Weather": {"SPY": 0.3, "TLT": 0.4, "IEF": 0.15, "GLD": 0.075, "GSG": 0.075},
        "Permanent": {"SPY": 0.25, "TLT": 0.25, "GLD": 0.25, "BIL": 0.25} # BIL proxy needed or CASH
    }
    
    # Simple test run
    # res = engine.compare_portfolios(ports, start_date="2000-01-01")
    # print(res["60/40"]["cagr"])
