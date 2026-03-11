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
from typing import List, Dict, Optional
from data_collectors.supabase_manager import SupabaseManager

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
        slippage: float = 0.0003,      # 0.03% (ETF는 유동성이 좋아 더 낮게 설정 가능)
        commission: float = 0.0001,   # 0.01% (미국 ETF 기준 저렴한 수수료)
        tax_rate: float = 0.0,         # 0.0% (ETF 거래세 면제 반영)
        rebalance_freq: str = "W-MON"
    ):
        self.initial_capital = initial_capital
        self.slippage = slippage
        self.commission = commission
        self.tax_rate = tax_rate
        self.rebalance_freq = rebalance_freq
        
        self.logger = logging.getLogger("PortfolioEngine")
        self.db = SupabaseManager()
        
        # 초장기 백테스트를 위한 지수 합성 매핑 (3x 레버리지 -> 1x 기초지수)
        self.synthetic_mapping = {
            "TQQQ": "QQQ",
            "SOXL": "^SOX", # 필라델피아 반도체 지수
            "FNGU": "^NYFANG", # NY FANG+ Index
            "UPRO": "SPY",
            "TMF": "TLT",
            "TYD": "IEF",
            "URTY": "IWM",   # 러셀 2000 3배
            "UDOW": "DIA",   # 다우 3배
        }

    def get_all_strategy_configs(self) -> List[Dict]:
        """전략들의 설정을 반환 (ExecutionDriver 호환용)"""
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
            }
        ]

    def fetch_multi_data(self, tickers: List[str], period: str = "max", interval: str = "1d") -> Dict[str, pd.DataFrame]:
        """여러 티커의 데이터를 수집 (초장기 백테스트를 위해 period='max' 기본값 사용)"""
        self.logger.info(f"Fetching data for {tickers}...")
        data = {}
        for t in tickers:
            try:
                # 1차 시도: yf.download
                df = yf.download(t, period=period, interval=interval, progress=False)
                
                # 데이터가 너무 짧거나 없는 경우 기초지수로 합성 시도
                if (df.empty or len(df) < 500) and t in self.synthetic_mapping:
                    base_ticker = self.synthetic_mapping[t]
                    if base_ticker != t:
                        self.logger.info(f"Synthesizing {t} from {base_ticker} for historical coverage...")
                        base_df = yf.download(base_ticker, period=period, interval=interval, progress=False)
                        if not base_df.empty:
                            # 단순 3배 합성 (초장기 경향성 파악용)
                            base_returns = base_df['Close'].pct_change()
                            synth_returns = base_returns * 3.0
                            # 기존 데이터가 있다면 끝부분만 교체, 없다면 전체 생성
                            last_price = df['Close'].iloc[0] if not df.empty else 100.0
                            # 여기서는 간략히 전체 시계열을 기초지수 변동률로 복원
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
        """
        [Macro Guard 2.0] 매크로 리스크 복합 점수 산출 (0.0 ~ 1.0)
        - 0.85 이상: 'Survival Trigger' 발동 (강제 대피)
        - CrisisAnalyzer와 연동하여 시스템적 위기 전조 통합 관리
        """
        try:
            from analysis.crisis_analyzer import CrisisAnalyzer
            analyzer = CrisisAnalyzer()
            crisis_res = analyzer.analyze_current_market()
            crisis_score = crisis_res.get('total_risk', 0.5)
            
            # 1. Liquidity Defense (30%)
            liq_score = 0.5
            liq_df = self.db.get_macro_history("NET_LIQUIDITY", days=90)
            if liq_df is not None and len(liq_df) > 10:
                recent_liq = liq_df.loc[:dt].tail(20)
                if len(recent_liq) > 2:
                    slope = np.polyfit(range(len(recent_liq)), recent_liq['value'], 1)[0]
                    liq_score = 0.9 if slope < 0 else 0.1

            # 2. Systemic Stress Defense (30%) - NFCI, TED Spread, HY Spread
            stress_score = 0.5
            nfci_df = self.db.get_macro_history("NFCI", days=60)
            ted_df = self.db.get_macro_history("TEDRATE", days=60)
            hy_df = self.db.get_macro_history("BAMLH0A0HYM2", days=60)
            
            nfci_val = nfci_df.loc[:dt, 'value'].iloc[-1] if nfci_df is not None and not nfci_df.empty else -0.5
            ted_val = ted_df.loc[:dt, 'value'].iloc[-1] if ted_df is not None and not ted_df.empty else 0.2
            hy_val = hy_df.loc[:dt, 'value'].iloc[-1] if hy_df is not None and not hy_df.empty else 4.0
            
            # NFCI는 0 이상이면 긴박, TED는 0.5 이상이면 위험, HY는 6.0 이상이면 위험
            s1 = np.clip((nfci_val + 1) / 2.0, 0, 1) # NFCI -1~1 -> 0~1
            s2 = np.clip(ted_val / 1.0, 0, 1)        # TED 0~1%
            s3 = np.clip((hy_val - 3.5) / 4.0, 0, 1) # HY 3.5%~7.5%
            stress_score = (s1 * 0.4) + (s2 * 0.3) + (s3 * 0.3)

            # 3. Structural Risk Defense (30%) - Yield Curve (T10Y2Y), DXY
            structural_score = 0.5
            ycurve_df = self.db.get_macro_history("T10Y2Y", days=180)
            dxy_df = self.db.get_macro_history("DX-Y.NYB", days=60)
            
            y_val = ycurve_df.loc[:dt, 'value'].iloc[-1] if ycurve_df is not None and not ycurve_df.empty else 1.0
            dxy_score = 0.5
            if dxy_df is not None and len(dxy_df) > 10:
                recent_dxy = dxy_df.loc[:dt].tail(20)
                slope_dxy = np.polyfit(range(len(recent_dxy)), recent_dxy['value'], 1)[0]
                dxy_score = 0.8 if slope_dxy > 0 else 0.2
            
            # Yield Curve: 역전 후 정상화(Un-inversion) 시점이 가장 위험 (0.0~0.2 구간)
            y_score = 0.2
            if y_val < 0: y_score = 0.7 # 역전 시 주의
            elif 0 <= y_val < 0.3: # 정상화 초기 (침체 직전)
                y_score = 0.9
            
            structural_score = (y_score * 0.7) + (dxy_score * 0.3)

            # 4. 종합 점수 (CrisisAnalyzer 점수와 가중 평균)
            # CrisisAnalyzer는 역사적 버블/취약성을, 기존 로직은 실시간 유동성/스트레스를 측정
            total_score = (crisis_score * 0.4) + (liq_score * 0.2) + (stress_score * 0.2) + (structural_score * 0.2)
            
            if total_score > 0.8:
                self.logger.warning(f"!!! Macro Crisis Alert !!! Total Score: {total_score:.2f} (Crisis: {crisis_score:.2f})")
                
            return float(total_score)
        except Exception as e:
            self.logger.error(f"Macro Score Calc Error: {e}")
            return 0.5

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """상대강도(ROC), 변동성 및 이동평균선 계산"""
        df = df.copy()
        # 20일 ROC (상대강도 지표)
        df['roc_20'] = df['Close'].pct_change(periods=20) * 100
        # 200일 SMA (시장 국면 필터용)
        df['sma_200'] = df['Close'].rolling(window=200).mean()
        # 60일 변동성 (리스크 패리티용)
        df['volatility_60'] = df['Close'].pct_change().rolling(window=60).std() * np.sqrt(252) * 100
        return df

    def calculate_risk_parity_weights(self, tickers: List[str], data: Dict[str, pd.DataFrame], dt: pd.Timestamp) -> Dict[str, float]:
        """변동성 역수에 비례하는 리스크 패리티 가중치 산출"""
        vols = {}
        for t in tickers:
            vol_val = data[t].loc[dt, 'volatility_60']
            vol = float(vol_val.iloc[0]) if isinstance(vol_val, pd.Series) else float(vol_val)
            if not np.isnan(vol) and vol > 0:
                vols[t] = 1.0 / vol
        
        if not vols:
            return {}
            
        total_inv_vol = sum(vols.values())
        return {t: inv_vol / total_inv_vol for t, inv_vol in vols.items()}

    def maximize_sharpe_ratio(self, tickers: List[str], data: Dict[str, pd.DataFrame], dt: pd.Timestamp) -> Dict[str, float]:
        """Sharpe Ratio를 극대화하는 MVO 가중치 산출 (Shrinkage 적용)"""
        # dt 전일(t-1)까지의 데이터만 사용하여 룩어헤드 편향 방지
        returns_df = pd.DataFrame()
        for t in tickers:
            # dt 포함이 아닌 dt 이전 데이터를 가져오기 위해 index 사용
            subset = data[t].loc[:dt]
            if len(subset) < 2: continue
            # dt 당일 데이터를 제외한 t-1까지의 수익률 계산
            prices = subset['Close'].iloc[:-1].tail(60) 
            returns_df[t] = prices.pct_change().dropna()
        
        if returns_df.empty or len(returns_df) < 20:
            return {}

        expected_returns = returns_df.mean() * 252
        
        # [Shrinkage 적용] Ledoit-Wolf 방식의 간소화된 구현
        sample_cov = returns_df.cov() * 252
        delta = 0.1  # Shrinkage coefficient (안정성을 위해 10% 정도 Target matrix 혼합)
        prior = np.diag(np.diag(sample_cov)) # Target: Diagonal matrix (Zero correlation)
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
            if opt_res.success:
                return {tickers[i]: float(opt_res.x[i]) for i in range(num_assets)}
        except Exception as e:
            self.logger.error(f"MVO Optimization Error: {e}")
        
        return {}

    def run_simulation(
        self, 
        alpha_tickers: List[str], 
        insurance_tickers: List[str],
        start_date: str = "2020-01-01",
        churn_threshold: float = 5.0,
        strategy_type: str = "dynamic",  # "dynamic" or "static"
        freq_override: str = None,
        custom_weights: Dict[str, float] = None
    ) -> Dict:
        """포트폴리오 시뮬레이션 수행"""
        reb_freq = freq_override if freq_override else self.rebalance_freq
        
        # 모든 필요한 티커 수집
        all_tickers = list(set(alpha_tickers + insurance_tickers + ["SPY"]))
        if custom_weights:
            all_tickers = list(set(all_tickers + list(custom_weights.keys())))
        
        raw_data = self.fetch_multi_data(all_tickers)
        
        processed_data = {}
        for t, df in raw_data.items():
            if not df.empty:
                processed_data[t] = self.calculate_indicators(df)
        
        # 유효한 데이터가 있는 티커들만 필터링
        valid_tickers = [t for t in all_tickers if t in processed_data]
        if "SPY" not in processed_data:
             return {"error": "SPY data (benchmark) is missing. Cannot proceed."}
        
        common_index = processed_data["SPY"].index
        for t in valid_tickers:
            common_index = common_index.intersection(processed_data[t].index)
        common_index = common_index[common_index >= start_date]
        
        if len(common_index) == 0:
            return {"error": "No common data available for the given start date."}

        rebalance_dates = pd.date_range(start=common_index[0], end=common_index[-1], freq=reb_freq)
        
        capital = self.initial_capital
        current_portfolio = {} # {ticker: shares}
        history = []
        
        for dt in common_index:
            is_rebalance_day = dt in rebalance_dates
            
            # 현재 가치 계산
            total_value = capital
            for t, shares in list(current_portfolio.items()):
                if t in processed_data and dt in processed_data[t].index:
                    price_val = processed_data[t].loc[dt, 'Close']
                    price = float(price_val.iloc[0]) if isinstance(price_val, pd.Series) else float(price_val)
                    total_value += shares * price
                else:
                    # 데이터가 일시적으로 없는 경우 이전 가치를 유지하거나 캐시(미구현)를 사용할 수 있으나
                    # 여기서는 안전하게 마지막 알려진 가격이 capital에 포함되어 있다고 가정 (또는 해당 자산 제외)
                    pass
            
            if is_rebalance_day:
                target_weights = {}
                
                if strategy_type == "dynamic":
                    # dt 전일 데이터 기반 시그널 생성 (룩어헤드 방어)
                    prev_idx = common_index.get_loc(dt) - 1
                    if prev_idx >= 0:
                        prev_dt = common_index[prev_idx]
                        spy_close = float(processed_data["SPY"].loc[prev_dt, 'Close'].iloc[0]) if isinstance(processed_data["SPY"].loc[prev_dt, 'Close'], pd.Series) else float(processed_data["SPY"].loc[prev_dt, 'Close'])
                        spy_sma = float(processed_data["SPY"].loc[prev_dt, 'sma_200'].iloc[0]) if isinstance(processed_data["SPY"].loc[prev_dt, 'sma_200'], pd.Series) else float(processed_data["SPY"].loc[prev_dt, 'sma_200'])
                        is_bull = spy_close > spy_sma
                        
                        if is_bull:
                            ranks = []
                            for t in alpha_tickers:
                                if t in processed_data and prev_dt in processed_data[t].index:
                                    roc_val = processed_data[t].loc[prev_dt, 'roc_20']
                                    roc = float(roc_val.iloc[0]) if isinstance(roc_val, pd.Series) else float(roc_val)
                                    if not np.isnan(roc):
                                        ranks.append((t, roc))
                            if ranks:
                                ranks.sort(key=lambda x: x[1], reverse=True)
                                target_weights = {ranks[0][0]: 1.0}
                        else:
                            safety_t = insurance_tickers[0] if insurance_tickers else "GLD"
                            target_weights = {safety_t: 1.0}
                elif strategy_type == "heag":
                    # HEAG (Hyper-Efficient Anti-Gravity) 로직
                    prev_idx = common_index.get_loc(dt) - 1
                    if prev_idx >= 0:
                        prev_dt = common_index[prev_idx]
                        active_assets = []
                        for t in alpha_tickers:
                            if t in processed_data and prev_dt in processed_data[t].index:
                                close_val = processed_data[t].loc[prev_dt, 'Close']
                                sma_val = processed_data[t].loc[prev_dt, 'sma_200']
                                close = float(close_val.iloc[0]) if isinstance(close_val, pd.Series) else float(close_val)
                                sma = float(sma_val.iloc[0]) if isinstance(sma_val, pd.Series) else float(sma_val)
                                if close > sma: 
                                    active_assets.append(t)
                        
                        if active_assets:
                            target_weights = self.calculate_risk_parity_weights(active_assets, processed_data, prev_dt)
                        else:
                            safety_t = insurance_tickers[0] if insurance_tickers else "GLD"
                            target_weights = {safety_t: 1.0}
                elif strategy_type == "aga":
                    # AGA (Anti-Gravity Alpha) MVO 최적화 로직
                    prev_idx = common_index.get_loc(dt) - 1
                    if prev_idx >= 0:
                        prev_dt = common_index[prev_idx]
                        active_assets = []
                        for t in alpha_tickers:
                            if t in processed_data and prev_dt in processed_data[t].index:
                                close_val = processed_data[t].loc[prev_dt, 'Close']
                                sma_val = processed_data[t].loc[prev_dt, 'sma_200']
                                close = float(close_val.iloc[0]) if isinstance(close_val, pd.Series) else float(close_val)
                                sma = float(sma_val.iloc[0]) if isinstance(sma_val, pd.Series) else float(sma_val)
                                if close > sma: 
                                    active_assets.append(t)
                        
                        if active_assets:
                            target_weights = self.maximize_sharpe_ratio(active_assets, processed_data, dt)
                            if not target_weights: 
                                target_weights = self.calculate_risk_parity_weights(active_assets, processed_data, prev_dt)
                            
                            # [Macro Guard 3.0] CDM 3.0 연동 정밀 비중 조절 (10% 단위 단계별 축소)
                            risk_res = self.get_macro_risk_score(dt)
                            # risk_score가 0.4(Caution)부터 10%씩 축소, 0.8(Survival)이면 100% 대피
                            risk_score = float(risk_res) if isinstance(risk_res, (float, int)) else 0.5
                            
                            if risk_score > 0.8:
                                # [Survival Trigger] 100% 안전자산 대피
                                safety_asset = insurance_tickers[0] if insurance_tickers else "GLD"
                                target_weights = {safety_asset: 1.0}
                                self.logger.warning(f"!!! SURVIVAL TRIGGER !!! Risk={risk_score:.2f} -> Full Exit")
                            elif risk_score > 0.4:
                                # 0.4 ~ 0.8 구간에서 10% 단위로 단계별 축소 (Staged De-risking)
                                # 예: 0.5 -> 75% 유지, 0.6 -> 50% 유지, 0.7 -> 25% 유지
                                reduction_steps = int((risk_score - 0.4) / 0.1) # 0, 1, 2, 3, 4
                                keep_factor = max(0.0, 1.0 - (reduction_steps * 0.25)) # 1.0, 0.75, 0.5, 0.25, 0.0
                                
                                new_target = {}
                                remaining_weight = 1.0
                                for t, w in target_weights.items():
                                    new_w = w * keep_factor
                                    new_target[t] = new_w
                                    remaining_weight -= new_w
                                
                                safety_asset = insurance_tickers[0] if insurance_tickers else "GLD"
                                new_target[safety_asset] = new_target.get(safety_asset, 0) + remaining_weight
                                target_weights = new_target
                                self.logger.info(f"CDM 3.0 De-risking: Risk={risk_score:.2f}, KeepFactor={keep_factor:.2f}")
                        else:
                            target_weights = {insurance_tickers[0]: 1.0}
                else:
                    # 정적 배분 로직
                    if custom_weights:
                        target_weights = custom_weights
                    else:
                        combined_assets = alpha_tickers + insurance_tickers
                        weight = 1.0 / len(combined_assets)
                        target_weights = {t: weight for t in combined_assets}

                # 교체 및 리밸런싱 실행
                current_assets = list(current_portfolio.keys())
                should_rebalance = False
                
                if not current_assets:
                    should_rebalance = True
                elif strategy_type in ["static", "heag", "aga"]:
                    should_rebalance = True # HEAG/AGA는 리스크/수익 변화에 따라 매 주기 리밸런싱
                elif set(current_assets) != set(target_weights.keys()):
                    if strategy_type == "dynamic":
                        # Churn Filter 적용
                        if list(target_weights.keys())[0] in alpha_tickers and current_assets[0] in alpha_tickers:
                            curr_roc_val = processed_data[current_assets[0]].loc[dt, 'roc_20']
                            target_roc_val = processed_data[list(target_weights.keys())[0]].loc[dt, 'roc_20']
                            curr_roc = float(curr_roc_val.iloc[0]) if isinstance(curr_roc_val, pd.Series) else float(curr_roc_val)
                            target_roc = float(target_roc_val.iloc[0]) if isinstance(target_roc_val, pd.Series) else float(target_roc_val)
                            if (target_roc - curr_roc) > churn_threshold:
                                should_rebalance = True
                        else:
                            should_rebalance = True
                
                if should_rebalance:
                    # 전량 매도 후 재배분
                    new_capital = total_value
                    # 매도 비용 (간략화를 위해 전체 매도 후 매수 시뮬레이션)
                    for t, shares in current_portfolio.items():
                        if t in processed_data and dt in processed_data[t].index:
                            price_val = processed_data[t].loc[dt, 'Close']
                            exit_price = float(price_val.iloc[0]) if isinstance(price_val, pd.Series) else float(price_val)
                            sell_val = shares * exit_price * (1 - self.slippage)
                            cost = sell_val * (self.commission + self.tax_rate)
                            new_capital -= cost
                    
                    # 매수
                    current_portfolio = {}
                    for t, weight in target_weights.items():
                        if t in processed_data and dt in processed_data[t].index:
                            price_val = processed_data[t].loc[dt, 'Close']
                            entry_price = float(price_val.iloc[0]) if isinstance(price_val, pd.Series) else float(price_val)
                            if entry_price <= 0.01: continue # 가격이 비정상적으로 낮으면 매수 보류 (오버플로우 방지)
                            
                            target_val = (new_capital * weight)
                            buy_price = entry_price * (1 + self.slippage)
                            shares = (target_val / (buy_price * (1 + self.commission)))
                            current_portfolio[t] = shares
                        else:
                            # 타겟 자산 데이터가 없으면 현금으로 보유
                            capital += (new_capital * weight)
                    
                    if capital < 0: capital = 0 # 보정

            history.append({"date": dt, "total_value": total_value})

        history_df = pd.DataFrame(history).set_index("date")
        final_return = (history_df['total_value'].iloc[-1] / self.initial_capital - 1) * 100
        spy_start_val = processed_data["SPY"].loc[common_index[0], 'Close']
        spy_end_val = processed_data["SPY"].loc[common_index[-1], 'Close']
        spy_start = float(spy_start_val.iloc[0]) if isinstance(spy_start_val, pd.Series) else float(spy_start_val)
        spy_end = float(spy_end_val.iloc[0]) if isinstance(spy_end_val, pd.Series) else float(spy_end_val)
        spy_return = (spy_end / spy_start - 1) * 100
        
        # MDD 계산
        rolling_max = history_df['total_value'].cummax()
        drawdown = (history_df['total_value'] - rolling_max) / rolling_max
        max_drawdown = drawdown.min() * 100
        
        return {
            "final_value": float(history_df['total_value'].iloc[-1]),
            "total_return_pct": float(final_return),
            "spy_return_pct": float(spy_return),
            "max_drawdown": float(max_drawdown),
            "history": history_df
        }

if __name__ == "__main__":
    engine = PortfolioEngine(initial_capital=10000.0)
    
    # 전략 정의
    configs = [
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
        }
    ]
    
    print("\n[Ray Dalio All-Weather vs Dynamic Strategy Comparison]")
    print("-" * 75)
    print(f"{'Strategy Name':<18} | {'Return':<10} | {'MDD':<10} | {'Bench':<10}")
    print("-" * 75)
    
    # 모든 구성 티커 수집 (공통 인덱스 확보용)
    all_needed_tickers = set()
    for cfg in configs:
        if cfg["alpha"]: all_needed_tickers.update(cfg["alpha"])
        if cfg["ins"]: all_needed_tickers.update(cfg["ins"])
        if cfg["weights"]: all_needed_tickers.update(cfg["weights"].keys())
    all_needed_tickers.add("SPY")
    
    # 공통 시작일 강제 (가장 늦게 상장된 종목 기준)
    master_raw = engine.fetch_multi_data(list(all_needed_tickers))
    valid_dfs = {t: df for t, df in master_raw.items() if not df.empty}
    
    if "SPY" in valid_dfs:
        common_idx = valid_dfs["SPY"].index
        # 필수 자산군(SPY, TLT 등) 외 유동적인 자산군에 대해서는 공통 인덱스를 너무 엄격하게 적용하지 않음
        # 여기서는 최소한 SPY 데이터는 있는 구간으로 설정
        actual_start = common_idx[0].strftime("%Y-%m-%d")
        print(f"Simulation Period: {actual_start} ~ {common_idx[-1].strftime('%Y-%m-%d')}")
    
    if len(common_idx) > 0:
        actual_start = common_idx[0].strftime("%Y-%m-%d")
        print(f"Simulation Period: {actual_start} ~ {common_idx[-1].strftime('%Y-%m-%d')}")
        print("-" * 75)
        
        for cfg in configs:
            res = engine.run_simulation(
                alpha_tickers=cfg["alpha"],
                insurance_tickers=cfg["ins"],
                start_date=actual_start,
                strategy_type=cfg["type"],
                freq_override=cfg["freq"],
                custom_weights=cfg["weights"]
            )
            if "error" not in res:
                print(f"{cfg['name']:<18} | {res['total_return_pct']:>8.2f}% | {res['max_drawdown']:>8.2f}% | {res['spy_return_pct']:>8.2f}%")
            else:
                print(f"{cfg['name']:<18} | ERROR")
    else:
        print("Error: No common historical data found for all tickers.")
