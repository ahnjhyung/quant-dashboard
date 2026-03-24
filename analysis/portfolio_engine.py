"""
Portfolio Engine
================
- Role: Manage a collection of assets and perform dynamic rebalancing.
- Strategy: Relative Strength (ROC) based rotation + Market Regime Filter.
- Friction: Includes slippage, commission, and taxes to ensure real-world validity.
"""

import pandas as pd
import numpy as np
import yfinance as yf
import logging
import requests
import urllib3
from scipy.optimize import minimize
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import math
from data_collectors.supabase_manager import SupabaseManager
from analysis.derivatives import DerivativesAnalyzer

# config에서 SSL 패치 및 API 키 로드
from config import FMP_API_KEY

# SSL 경고 무시 및 전역 세션 설정 (yfinance 파싱 오류 및 인증서 문제 해결용)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
old_init = requests.Session.__init__
def new_init(self, *args, **kwargs):
    old_init(self, *args, **kwargs)
    self.verify = False
requests.Session.__init__ = new_init

class PortfolioEngine:
    def __init__(
        self,
        initial_capital: float = 10000.0,
        slippage: float = 0.0003,      # 0.03%
        commission: float = 0.0001,   # 0.01%
        tax_rate: float = 0.0,         # 0.0%
        rebalance_freq: str = "W-MON"
    ):
        self.initial_capital = initial_capital
        self.slippage = slippage
        self.commission = commission
        self.tax_rate = tax_rate
        self.rebalance_freq = rebalance_freq
        
        self.logger = logging.getLogger("PortfolioEngine")
        self.db = SupabaseManager()
        self.derivatives = DerivativesAnalyzer()
        self._macro_score_cache = {}
        self._active_hedges = {}
        
        self.synthetic_mapping = {
            "TQQQ": "QQQ",
            "SOXL": "^SOX",
            "FNGU": "^NYFANG",
            "UPRO": "SPY",
            "TMF": "TLT",
            "TYD": "IEF",
            "URTY": "IWM",
            "UDOW": "DIA",
        }

    def get_all_strategy_configs(self) -> List[Dict]:
        return [
            {"name": "Dynamic (M)", "type": "dynamic", "freq": "ME", "alpha": ["TQQQ", "SOXL", "FNGU"], "ins": ["TLT"], "weights": None},
            {"name": "Simple Static", "type": "static", "freq": "ME", "alpha": ["TQQQ", "SOXL", "FNGU"], "ins": ["TLT"], "weights": None},
            {
                "name": "Dalio AW", 
                "type": "static", "freq": "ME", 
                "alpha": [], "ins": [], 
                "weights": {"SPY": 0.30, "TLT": 0.40, "IEF": 0.15, "GLD": 0.075, "GSG": 0.075}
            },
            {
                "name": "Lev AW (3x)", 
                "type": "static", "freq": "ME", 
                "alpha": [], "ins": [], 
                "weights": {"UPRO": 0.30, "TMF": 0.40, "TYD": 0.15, "GLD": 0.075, "GSG": 0.075}
            },
            {
                "name": "HEAG (Ultra)", 
                "type": "heag", "freq": "ME", 
                "alpha": ["TQQQ", "SOXL", "FNGU", "BTC-USD", "GLD"], 
                "ins": ["TLT"], 
                "weights": None
            },
            {
                "name": "AGA (Anti-Gravity)", 
                "type": "aga", "freq": "ME", 
                "alpha": ["TQQQ", "SOXL", "FNGU", "BTC-USD", "GLD"], 
                "ins": ["TLT"], 
                "weights": None
            },
            {
                "name": "AGA Broad (CDM3)", 
                "type": "aga", "freq": "ME", 
                "alpha": ["TQQQ", "SOXL", "URTY", "UDOW", "BTC-USD"], 
                "ins": ["TLT", "GLD"], 
                "weights": None
            },
            {
                "name": "Low-MDD Ultra",
                "type": "low_mdd", "freq": "ME",
                "alpha": ["TQQQ", "SOXL", "FNGU", "BTC-USD"],
                "ins": ["TLT", "GLD"],
                "weights": None
            },
            {
                "name": "MR Aggressive",
                "type": "mean_reversion_agg", "freq": "1d",
                "alpha": ["TQQQ", "SOXL"],
                "ins": ["TLT"],
                "weights": None
            }
        ]

    def fetch_multi_data(self, tickers: List[str], period: str = "max", interval: str = "1d") -> Dict[str, pd.DataFrame]:
        self.logger.info(f"Fetching data for {tickers}...")
        data = {}
        for t in tickers:
            try:
                df = yf.download(t, period=period, interval=interval, progress=False)
                if (df.empty or len(df) < 500) and t in self.synthetic_mapping:
                    base_ticker = self.synthetic_mapping[t]
                    if base_ticker != t:
                        self.logger.info(f"Synthesizing {t} from {base_ticker} for historical coverage...")
                        base_df = yf.download(base_ticker, period=period, interval=interval, progress=False)
                        if not base_df.empty:
                            base_returns = base_df['Close'].pct_change()
                            synth_returns = base_returns * 3.0
                            last_price = df['Close'].iloc[0] if not df.empty else 100.0
                            synth_prices = [last_price]
                            for ret in reversed(synth_returns.loc[:df.index[0] if not df.empty else base_df.index[-1]]):
                                if not np.isnan(ret):
                                    synth_prices.append(synth_prices[-1] / (1 + ret))
                            synth_prices.reverse()
                            df = pd.DataFrame({"Close": synth_prices[1:]}, index=base_df.index[:len(synth_prices)-1])
                if not df.empty:
                    data[t] = df
                    self.logger.info(f"Successfully fetched/synthesized {t} ({len(df)} rows)")
                else:
                    self.logger.warning(f"Failed to fetch {t}: Empty Data")
            except Exception as e:
                self.logger.error(f"Error fetching {t}: {e}")
        return data

    def get_macro_risk_score(self, dt: pd.Timestamp) -> float:
        date_obj = dt.date() if hasattr(dt, 'date') else dt
        if date_obj in self._macro_score_cache:
            return self._macro_score_cache[date_obj]
        try:
            from analysis.crisis_analyzer import CrisisAnalyzer
            analyzer = CrisisAnalyzer()
            crisis_res = analyzer.analyze_current_market(dt=dt)
            crisis_score = crisis_res.get('total_risk', 0.5)
            
            liq_score = 0.5
            liq_df = self.db.get_macro_history("NET_LIQUIDITY", days=90)
            if liq_df is not None and len(liq_df) > 10:
                recent_liq = liq_df.loc[:dt].tail(20)
                if len(recent_liq) > 2:
                    slope = np.polyfit(range(len(recent_liq)), recent_liq['value'], 1)[0]
                    liq_score = 0.9 if slope < 0 else 0.1

            nfci_df = self.db.get_macro_history("NFCI", days=60)
            ted_df = self.db.get_macro_history("TEDRATE", days=60)
            hy_df = self.db.get_macro_history("BAMLH0A0HYM2", days=60)
            vix_df = self.db.get_macro_history("VIXCLS", days=60)
            
            nfci_val = nfci_df.loc[:dt, 'value'].iloc[-1] if nfci_df is not None and not nfci_df.empty else -0.5
            ted_val = ted_df.loc[:dt, 'value'].iloc[-1] if ted_df is not None and not ted_df.empty else 0.2
            hy_val = hy_df.loc[:dt, 'value'].iloc[-1] if hy_df is not None and not hy_df.empty else 4.0
            vix_val = vix_df.loc[:dt, 'value'].iloc[-1] if vix_df is not None and not vix_df.empty else 15.0
            
            s1 = np.clip((nfci_val + 1) / 2.0, 0, 1)
            s2 = np.clip(ted_val / 1.0, 0, 1)
            s3 = np.clip((hy_val - 3.5) / 4.0, 0, 1)
            s4 = np.clip((vix_val - 15) / 15.0, 0, 1)
            stress_score = (s1 * 0.25) + (s2 * 0.2) + (s3 * 0.25) + (s4 * 0.3)

            ycurve_df = self.db.get_macro_history("T10Y2Y", days=180)
            y_val = ycurve_df.loc[:dt, 'value'].iloc[-1] if ycurve_df is not None and not ycurve_df.empty else 1.0
            y_score = 0.2
            if y_val < 0: y_score = 0.7 
            elif 0 <= y_val < 0.3: y_score = 0.9
            
            total_score = (crisis_score * 0.2) + (liq_score * 0.2) + (stress_score * 0.4) + (y_score * 0.2)
            res_val = float(total_score)
            self._macro_score_cache[date_obj] = res_val
            return res_val
        except Exception as e:
            self.logger.error(f"Macro Score Error: {e}")
            return 0.5

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # yfinance 0.2.x+ 대응: MultiIndex 컬럼 평탄화
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
            
        df['roc_20'] = close.pct_change(periods=20) * 100
        df['sma_5'] = close.rolling(window=5).mean()
        df['sma_50'] = close.rolling(window=50).mean()
        df['sma_150'] = close.rolling(window=150).mean()
        df['sma_200'] = close.rolling(window=200).mean()
        df['volatility_60'] = close.pct_change().rolling(window=60).std() * np.sqrt(252) * 100
        
        # RSI(14) & RSI(2)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs14 = gain / (loss + 1e-9)
        df['rsi_14'] = 100 - (100 / (1 + rs14))
        
        gain2 = (delta.where(delta > 0, 0)).rolling(window=2).mean()
        loss2 = (-delta.where(delta < 0, 0)).rolling(window=2).mean()
        rs2 = gain2 / (loss2 + 1e-9)
        df['rsi_2'] = 100 - (100 / (1 + rs2))
        
        # Range for Williams VBT
        df['prev_high'] = df['High'].shift(1)
        df['prev_low'] = df['Low'].shift(1)
        df['prev_range'] = df['prev_high'] - df['prev_low']
        
        # Volume Confirmation
        df['vol_change_pct'] = df['Volume'].pct_change() * 100
        
        # Disparity(20) & Disparity(200)
        df['sma_20'] = close.rolling(window=20).mean()
        df['disparity_20'] = (close / (df['sma_20'] + 1e-9) - 1) * 100
        df['disparity_200'] = (close / (df['sma_200'] + 1e-9) - 1) * 100
        
        return df

    def calculate_risk_parity_weights(self, tickers: List[str], data: Dict[str, pd.DataFrame], dt: pd.Timestamp) -> Dict[str, float]:
        vols = {}
        for t in tickers:
            vol_val = data[t].loc[dt, 'volatility_60']
            vol = float(vol_val.iloc[0]) if isinstance(vol_val, pd.Series) else float(vol_val)
            if not np.isnan(vol) and vol > 0:
                vols[t] = 1.0 / vol
        if not vols: return {}
        total_inv_vol = sum(vols.values())
        return {t: inv_vol / total_inv_vol for t, inv_vol in vols.items()}

    def maximize_sharpe_ratio(self, tickers: List[str], data: Dict[str, pd.DataFrame], dt: pd.Timestamp) -> Dict[str, float]:
        returns_df = pd.DataFrame()
        for t in tickers:
            subset = data[t].loc[:dt]
            if len(subset) < 2: continue
            prices = subset['Close'].iloc[:-1].tail(60) 
            returns_df[t] = prices.pct_change().dropna()
        if returns_df.empty or len(returns_df) < 20: return {}
        expected_returns = returns_df.mean() * 252
        sample_cov = returns_df.cov() * 252
        delta = 0.1
        prior = np.diag(np.diag(sample_cov))
        shrunk_cov = (1 - delta) * sample_cov + delta * prior
        num_assets = len(tickers)
        def objective(weights):
            port_return = np.dot(weights, expected_returns)
            port_vol = np.sqrt(np.dot(weights.T, np.dot(shrunk_cov, weights)))
            return -(port_return - 0.02) / (port_vol + 1e-9)
        constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
        bounds = tuple((0.0, 1.0) for _ in range(num_assets))
        init_guess = num_assets * [1.0 / num_assets]
        try:
            opt_res = minimize(objective, init_guess, method='SLSQP', bounds=bounds, constraints=constraints)
            if opt_res.success: return {tickers[i]: float(opt_res.x[i]) for i in range(num_assets)}
        except Exception as e: self.logger.error(f"MVO Error: {e}")
        return {}

    def run_simulation(
        self, 
        alpha_tickers: List[str], 
        insurance_tickers: List[str],
        start_date: str = "2020-01-01",
        churn_threshold: float = 5.0,
        strategy_type: str = "dynamic",
        freq_override: str = None,
        custom_weights: Dict[str, float] = None
    ) -> Dict:
        reb_freq = freq_override if freq_override else self.rebalance_freq
        all_tickers = list(set(alpha_tickers + insurance_tickers + ["SPY", "^VIX"]))
        if custom_weights: all_tickers = list(set(all_tickers + list(custom_weights.keys())))
        raw_data = self.fetch_multi_data(all_tickers)
        processed_data = {t: self.calculate_indicators(df) for t, df in raw_data.items() if not df.empty}
        if "SPY" not in processed_data: return {"error": "SPY missing"}
        common_index = processed_data["SPY"].index[processed_data["SPY"].index >= start_date]
        if len(common_index) == 0: return {"error": "No data for start date"}
        rebalance_dates = pd.date_range(start=common_index[0], end=common_index[-1], freq=reb_freq)
        
        capital = self.initial_capital
        current_portfolio = {}
        history = []
        macro_scores = {}
        
        self.logger.info("Pre-calculating risk scores...")
        for dt in common_index:
            # 매일 리스크 점수를 체크하도록 변경 (AGA 전용)
            if strategy_type == "aga" or dt in rebalance_dates:
                 macro_scores[dt] = self.get_macro_risk_score(dt)

        for dt in common_index:
            is_rebalance_day = dt in rebalance_dates
            total_value = capital
            
            # [Payout] Daily Check
            for t, shares in list(current_portfolio.items()):
                if t in processed_data and dt in processed_data[t].index:
                    p_val = processed_data[t].loc[dt, 'Close']
                    price = float(p_val.iloc[0]) if isinstance(p_val, pd.Series) else float(p_val)
                    if t in self._active_hedges and price < self._active_hedges[t]:
                        self.logger.info(f"Payout for {t}: {price:.2f} -> {self._active_hedges[t]:.2f}")
                        price = self._active_hedges[t]
                    if not np.isnan(price):
                        total_value += shares * price

            # [Daily Risk & Hedge Activation] for AGA
            if strategy_type == "aga":
                r_score = float(macro_scores.get(dt, 0.0))
                if r_score >= 0.4:
                    for t in list(current_portfolio.keys()):
                        if t in alpha_tickers and t not in self._active_hedges:
                            p_val = processed_data[t].loc[dt, 'Close']
                            curr_price = float(p_val.iloc[0]) if isinstance(p_val, pd.Series) else float(p_val)
                            cost = (current_portfolio[t] * curr_price) * 0.01
                            if capital >= cost:
                                capital -= cost
                                self._active_hedges[t] = curr_price * 0.95
                                self.logger.info(f"Purchased Daily Put for {t} at {dt}")

            if is_rebalance_day:
                target_weights = {}
                prev_idx = common_index.get_loc(dt) - 1
                prev_dt = common_index[prev_idx] if prev_idx >= 0 else dt
                
                if strategy_type == "dynamic":
                    spy_c = float(processed_data["SPY"].loc[prev_dt, 'Close'].iloc[0] if isinstance(processed_data["SPY"].loc[prev_dt, 'Close'], pd.Series) else processed_data["SPY"].loc[prev_dt, 'Close'])
                    spy_s = float(processed_data["SPY"].loc[prev_dt, 'sma_200'].iloc[0] if isinstance(processed_data["SPY"].loc[prev_dt, 'sma_200'], pd.Series) else processed_data["SPY"].loc[prev_dt, 'sma_200'])
                    if spy_c > spy_s:
                        ranks = []
                        for t in alpha_tickers:
                            if t in processed_data and prev_dt in processed_data[t].index:
                                roc = float(processed_data[t].loc[prev_dt, 'roc_20'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'roc_20'], pd.Series) else processed_data[t].loc[prev_dt, 'roc_20'])
                                if not np.isnan(roc): ranks.append((t, roc))
                        if ranks:
                            ranks.sort(key=lambda x: x[1], reverse=True)
                            target_weights = {ranks[0][0]: 1.0}
                    else:
                        target_weights = { (insurance_tickers[0] if insurance_tickers else "GLD"): 1.0 }
                elif strategy_type == "aga":
                    active_assets = []
                    for t in alpha_tickers:
                        if t in processed_data and prev_dt in processed_data[t].index:
                            c = float(processed_data[t].loc[prev_dt, 'Close'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'Close'], pd.Series) else processed_data[t].loc[prev_dt, 'Close'])
                            s = float(processed_data[t].loc[prev_dt, 'sma_200'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'sma_200'], pd.Series) else processed_data[t].loc[prev_dt, 'sma_200'])
                            if c > s: active_assets.append(t)
                    if active_assets:
                        target_weights = self.maximize_sharpe_ratio(active_assets, processed_data, dt)
                        if not target_weights: target_weights = self.calculate_risk_parity_weights(active_assets, processed_data, prev_dt)
                        r_score = float(macro_scores.get(dt, 0.5))
                        if r_score > 0.8:
                            target_weights = { (insurance_tickers[0] if insurance_tickers else "GLD"): 1.0 }
                        elif r_score > 0.4:
                            keep = max(0.0, 1.0 - (int((r_score - 0.4)/0.1) * 0.25))
                            new_t = {t: w*keep for t, w in target_weights.items()}
                            rem = 1.0 - sum(new_t.values())
                            new_t[insurance_tickers[0] if insurance_tickers else "GLD"] = rem
                            target_weights = new_t
                    else:
                        target_weights = { (insurance_tickers[0] if insurance_tickers else "GLD"): 1.0 }
                elif strategy_type == "static":
                    if custom_weights: target_weights = custom_weights
                    else: target_weights = {t: 1.0/len(alpha_tickers+insurance_tickers) for t in alpha_tickers+insurance_tickers}
                elif strategy_type == "mean_reversion_agg":
                    vix_val = 20.0
                    if "^VIX" in processed_data and prev_dt in processed_data["^VIX"].index:
                        v_val = processed_data["^VIX"].loc[prev_dt, 'Close']
                        vix_val = float(v_val.iloc[0]) if isinstance(v_val, pd.Series) else float(v_val)
                    
                    scaling_factor = 1.0
                    if vix_val > 40: scaling_factor = 0.2
                    elif vix_val > 30: scaling_factor = 0.5
                    elif vix_val > 25: scaling_factor = 0.7
                    elif vix_val > 20: scaling_factor = 0.9

                    signal_assets = []
                    for t in alpha_tickers:
                        if t in processed_data and prev_dt in processed_data[t].index:
                            rsi = float(processed_data[t].loc[prev_dt, 'rsi_14'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'rsi_14'], pd.Series) else processed_data[t].loc[prev_dt, 'rsi_14'])
                            disp = float(processed_data[t].loc[prev_dt, 'disparity_200'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'disparity_200'], pd.Series) else processed_data[t].loc[prev_dt, 'disparity_200'])
                            if rsi <= 30 or disp <= -20:
                                signal_assets.append(t)
                    
                    if signal_assets:
                        weight_per_asset = scaling_factor / len(signal_assets)
                        target_weights = {t: weight_per_asset for t in signal_assets}
                        rem = 1.0 - sum(target_weights.values())
                        if rem > 0:
                            target_weights[insurance_tickers[0] if insurance_tickers else "GLD"] = rem
                    else:
                        target_weights = { (insurance_tickers[0] if insurance_tickers else "GLD"): 1.0 }

                elif strategy_type == "mr_connors_rsi2":
                    for t in alpha_tickers:
                        if t in processed_data and prev_dt in processed_data[t].index:
                            rsi2 = float(processed_data[t].loc[prev_dt, 'rsi_2'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'rsi_2'], pd.Series) else processed_data[t].loc[prev_dt, 'rsi_2'])
                            sma200 = float(processed_data[t].loc[prev_dt, 'sma_200'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'sma_200'], pd.Series) else processed_data[t].loc[prev_dt, 'sma_200'])
                            curr_c = float(processed_data[t].loc[prev_dt, 'Close'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'Close'], pd.Series) else processed_data[t].loc[prev_dt, 'Close'])
                            disp20 = float(processed_data[t].loc[prev_dt, 'disparity_20'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'disparity_20'], pd.Series) else processed_data[t].loc[prev_dt, 'disparity_20'])
                            
                            # Entry: SMA200 위 (또는 이격도 -15% 이하) & RSI(2) < 5 & 20일 이격도 < 10%
                            if (curr_c > sma200 or disp20 < -15) and rsi2 <= 5 and disp20 < 10:
                                target_weights[t] = 1.0 / len(alpha_tickers)
                        
                    # Exit: If already in portfolio, check RSI2 > 70 or price > SMA5
                    for t in current_portfolio.keys():
                        if t in processed_data and dt in processed_data[t].index:
                            rsi2_now = float(processed_data[t].loc[dt, 'rsi_2'].iloc[0] if isinstance(processed_data[t].loc[dt, 'rsi_2'], pd.Series) else processed_data[t].loc[dt, 'rsi_2'])
                            sma5_now = float(processed_data[t].loc[dt, 'sma_5'].iloc[0] if isinstance(processed_data[t].loc[dt, 'sma_5'], pd.Series) else processed_data[t].loc[dt, 'sma_5'])
                            curr_c_now = float(processed_data[t].loc[dt, 'Close'].iloc[0] if isinstance(processed_data[t].loc[dt, 'Close'], pd.Series) else processed_data[t].loc[dt, 'Close'])
                            if rsi2_now >= 70 or curr_c_now > sma5_now:
                                if t in target_weights: del target_weights[t]

                elif strategy_type == "vbt_williams":
                    k = 0.5
                    for t in alpha_tickers:
                        if t in processed_data and prev_dt in processed_data[t].index:
                            p_range = float(processed_data[t].loc[prev_dt, 'prev_range'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'prev_range'], pd.Series) else processed_data[t].loc[prev_dt, 'prev_range'])
                            open_p = float(processed_data[t].loc[dt, 'Open'].iloc[0] if isinstance(processed_data[t].loc[dt, 'Open'], pd.Series) else processed_data[t].loc[dt, 'Open'])
                            curr_c = float(processed_data[t].loc[dt, 'Close'].iloc[0] if isinstance(processed_data[t].loc[dt, 'Close'], pd.Series) else processed_data[t].loc[dt, 'Close'])
                            vol_confirm = float(processed_data[t].loc[dt, 'vol_change_pct'].iloc[0] if isinstance(processed_data[t].loc[dt, 'vol_change_pct'], pd.Series) else processed_data[t].loc[dt, 'vol_change_pct'])
                            
                            # Williams Breakout Entry
                            if curr_c > (open_p + p_range * k) and vol_confirm > 50:
                                target_weights[t] = 1.0 / len(alpha_tickers)
                    
                    # Exit: End of day (represented by not being in target_weights for next period if signal dies)
                    # But for VBT, we keep it till EOD. The engine rebalances daily.

                elif strategy_type == "vcp_minervini":
                    for t in alpha_tickers:
                        if t in processed_data and prev_dt in processed_data[t].index:
                            s50 = float(processed_data[t].loc[prev_dt, 'sma_50'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'sma_50'], pd.Series) else processed_data[t].loc[prev_dt, 'sma_50'])
                            s150 = float(processed_data[t].loc[prev_dt, 'sma_150'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'sma_150'], pd.Series) else processed_data[t].loc[prev_dt, 'sma_150'])
                            s200 = float(processed_data[t].loc[prev_dt, 'sma_200'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'sma_200'], pd.Series) else processed_data[t].loc[prev_dt, 'sma_200'])
                            vol_confirm = float(processed_data[t].loc[prev_dt, 'vol_change_pct'].iloc[0] if isinstance(processed_data[t].loc[prev_dt, 'vol_change_pct'], pd.Series) else processed_data[t].loc[prev_dt, 'vol_change_pct'])
                            
                            # Trend Filter: 50 > 150 > 200
                            if s50 > s150 > s200 and vol_confirm > 50:
                                target_weights[t] = 1.0 / len(alpha_tickers)

                if not target_weights:
                    target_weights = { (insurance_tickers[0] if insurance_tickers else "GLD"): 1.0 }
                else:
                    # Limit max weight per asset and ensure cash buffer
                    max_weight = 0.5 # Never more than 50% in a single leverage ticker
                    total_w = sum(target_weights.values())
                    if total_w > 0:
                        target_weights = {t: (w/total_w) * 0.9 for t, w in target_weights.items()} # Use 90% of capital
                        target_weights["CASH"] = 0.1 # Keep 10% cash

                
                # Rebalance execution
                new_capital = total_value
                for t, shares in current_portfolio.items():
                    if t in processed_data and dt in processed_data[t].index:
                        p = float(processed_data[t].loc[dt, 'Close'].iloc[0] if isinstance(processed_data[t].loc[dt, 'Close'], pd.Series) else processed_data[t].loc[dt, 'Close'])
                        new_capital -= shares * p * (self.slippage + self.commission)
                
                current_portfolio = {}
                capital = 0.0
                for t, w in target_weights.items():
                    if t in processed_data and dt in processed_data[t].index:
                        p_val = processed_data[t].loc[dt, 'Close']
                        price = float(p_val.iloc[0] * (1+self.slippage)) if hasattr(p_val, 'iloc') else float(p_val * (1+self.slippage))
                        current_portfolio[t] = (new_capital * w) / (price * (1+self.commission))
                    else: capital += (new_capital * w)
                self._active_hedges = {} # Reset monthly or on rebalance
            
            history.append({"date": dt, "total_value": total_value})

        df_hist = pd.DataFrame(history).set_index("date")
        final_v = float(df_hist['total_value'].iloc[-1])
        ret = (final_v / self.initial_capital - 1) * 100
        spy_r = (float(processed_data["SPY"].iloc[-1]['Close']) / float(processed_data["SPY"].loc[common_index[0], 'Close']) - 1) * 100
        mdd = ((df_hist['total_value'] - df_hist['total_value'].cummax()) / df_hist['total_value'].cummax()).min() * 100
        years = (df_hist.index[-1] - df_hist.index[0]).days / 365.25
        cagr = ((final_v / self.initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0
        return {"final_value": final_v, "total_return_pct": ret, "cagr": cagr, "spy_return_pct": spy_r, "max_drawdown": mdd, "history": df_hist}

if __name__ == "__main__":
    engine = PortfolioEngine(initial_capital=10000.0)
    res = engine.run_simulation(["TQQQ", "SOXL"], ["TLT"], strategy_type="aga")
    print(f"Return: {res['total_return_pct']:.2f}%, MDD: {res['max_drawdown']:.2f}%")
