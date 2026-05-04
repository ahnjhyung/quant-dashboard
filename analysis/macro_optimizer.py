"""
Macro-Driven Portfolio Optimizer
================================
현재 매크로 지표(성장, 인플레이션, 유동성, 스트레스)를 종합 분석하여
Mean-Variance Optimization 기반 최적 포트폴리오를 추천하는 엔진.

EV 기준:
  EV = E[R_portfolio] - Rf
  → Sharpe Ratio 최대화 == 위험 단위당 EV 최대화와 동치
  → EV > 0 (포트폴리오 기대수익률 > 무위험이자율)인 배분만 추천
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from scipy.optimize import minimize
from data_collectors.supabase_manager import SupabaseManager
from data_collectors.yf_utils import download_ticker_data


@dataclass
class RegimeSnapshot:
    """현재 매크로 국면 요약."""
    regime: str           # Goldilocks / Reflation / Stagflation / Deflation
    growth_trend: bool    # True = 성장 상승 추세
    inflation_trend: bool # True = 인플레이션 상승 추세
    liquidity_score: float   # -1 ~ +1 (긴축 ~ 완화)
    stress_score: float      # 0 ~ 1 (저위험 ~ 고위험)
    details: Dict


class MacroOptimizer:
    """매크로 지표 기반 최적 포트폴리오 생성 엔진.

    Args:
        rf: 무위험 이자율 (연율, 기본 0.04 = 4%).
    """

    # 국면별 자산 유니버스 (EV가 양수일 것으로 기대되는 자산군 우선순위)
    REGIME_UNIVERSE = {
        "Goldilocks":  ["SPY", "QQQ", "IWM", "EFA", "GLD", "TLT", "IEF", "HYG"],
        "Reflation":   ["SPY", "IWM", "GSG", "GLD", "EFA", "HYG", "TIP", "IEF"],
        "Stagflation": ["GLD", "GSG", "TIP", "SHY", "IEF", "TLT", "SPY", "EFA"],
        "Deflation":   ["TLT", "IEF", "SHY", "GLD", "SPY", "AGG", "LQD", "EFA"],
    }

    # 국면별 자산 비중 상한 제약 (과도 집중 방지)
    REGIME_MAX_WEIGHT = {
        "Goldilocks":  0.40,
        "Reflation":   0.35,
        "Stagflation": 0.30,
        "Deflation":   0.35,
    }

    def __init__(self, rf: float = 0.04):
        self.rf = rf
        self.db = SupabaseManager()
        self.logger = logging.getLogger("MacroOptimizer")

    # ─── 1. 매크로 국면 진단 ───────────────────────────────────────────

    def diagnose_regime(self) -> RegimeSnapshot:
        """Supabase DB의 매크로 지표로 현재 국면을 진단한다.

        Returns:
            RegimeSnapshot: 현재 국면 정보.
        """
        details: Dict = {}

        # 성장 지표: INDPRO (산업생산지수) YoY 변화
        growth_df = self.db.get_macro_history("INDPRO", days=500)
        growth_trend = True  # 기본값
        growth_roc = 0.0
        if growth_df is not None and len(growth_df) >= 13:
            vals = growth_df["value"]
            growth_roc = (vals.iloc[-1] / vals.iloc[-13] - 1) * 100
            growth_ma = growth_df["value"].pct_change(12).rolling(3).mean()
            growth_trend = bool(growth_ma.iloc[-1] > growth_ma.median()) if not growth_ma.empty else True
            details["indpro_yoy"] = round(growth_roc, 2)

        # 인플레이션 지표: CPIAUCSL YoY 변화
        cpi_df = self.db.get_macro_history("CPIAUCSL", days=500)
        inflation_trend = False
        cpi_yoy = 0.0
        if cpi_df is not None and len(cpi_df) >= 13:
            vals = cpi_df["value"]
            cpi_yoy = (vals.iloc[-1] / vals.iloc[-13] - 1) * 100
            inflation_trend = bool(cpi_yoy > 3.0)
            details["cpi_yoy"] = round(cpi_yoy, 2)

        # 유동성 지표: NET_LIQUIDITY 추세
        liq_df = self.db.get_macro_history("NET_LIQUIDITY", days=200)
        liquidity_score = 0.0
        if liq_df is not None and len(liq_df) >= 20:
            liq_vals = liq_df["value"]
            liq_ma20 = liq_vals.rolling(20).mean()
            if liq_ma20.iloc[-1] > 0:
                liquidity_score = float(np.clip(
                    (liq_vals.iloc[-1] / liq_ma20.iloc[-1] - 1) * 10, -1, 1
                ))
            details["net_liquidity_trend"] = round(liquidity_score, 3)

        # 스트레스 지표: VIX, HY 스프레드
        vix_df = self.db.get_macro_history("VIXCLS", days=60)
        hy_df = self.db.get_macro_history("BAMLH0A0HYM2", days=60)
        stress_score = 0.3  # 기본 중립
        if vix_df is not None and not vix_df.empty:
            vix_val = float(vix_df["value"].iloc[-1])
            # VIX 15이하=저위험, 30이상=고위험
            vix_norm = float(np.clip((vix_val - 15) / 25, 0, 1))
            stress_score = vix_norm
            details["vix"] = round(vix_val, 1)

        if hy_df is not None and not hy_df.empty:
            hy_spread = float(hy_df["value"].iloc[-1])
            hy_norm = float(np.clip((hy_spread - 3) / 7, 0, 1))
            stress_score = (stress_score + hy_norm) / 2
            details["hy_spread"] = round(hy_spread, 2)

        details["stress_score"] = round(stress_score, 3)

        # 버핏 지표 수집: BUFFET_INDICATOR_US, BUFFET_INDICATOR_KR
        buffet_us_df = self.db.get_macro_history("BUFFET_INDICATOR_US", days=7)
        if buffet_us_df is not None and not buffet_us_df.empty:
            details["buffet_us"] = round(float(buffet_us_df["value"].iloc[-1]), 2)
        
        buffet_kr_df = self.db.get_macro_history("BUFFET_INDICATOR_KR", days=7)
        if buffet_kr_df is not None and not buffet_kr_df.empty:
            details["buffet_kr"] = round(float(buffet_kr_df["value"].iloc[-1]), 2)

        # 4사분면 국면 분류
        if growth_trend and not inflation_trend:
            regime = "Goldilocks"
        elif growth_trend and inflation_trend:
            regime = "Reflation"
        elif not growth_trend and inflation_trend:
            regime = "Stagflation"
        else:
            regime = "Deflation"

        details["regime"] = regime

        return RegimeSnapshot(
            regime=regime,
            growth_trend=growth_trend,
            inflation_trend=inflation_trend,
            liquidity_score=liquidity_score,
            stress_score=stress_score,
            details=details,
        )

    # ─── 2. Mean-Variance Optimization ─────────────────────────────────

    def _fetch_returns(
        self, tickers: List[str], lookback_years: int = 5
    ) -> pd.DataFrame:
        """yfinance에서 일별 수익률 데이터를 가져온다."""
        start = (pd.Timestamp.now() - pd.DateOffset(years=lookback_years)).strftime("%Y-%m-%d")
        all_prices = pd.DataFrame()
        for t in tickers:
            try:
                df = download_ticker_data(t, start=start)
                if df is not None and not df.empty:
                    if isinstance(df, pd.DataFrame):
                        if "Close" in df.columns:
                            series = df["Close"]
                        else:
                            series = df.iloc[:, 0]
                    else:
                        series = df
                    # flatten MultiIndex columns if needed
                    if hasattr(series, "columns"):
                        series = series.iloc[:, 0]
                    all_prices[t] = series
            except Exception as e:
                self.logger.warning(f"Failed to fetch {t}: {e}")

        if all_prices.empty:
            return pd.DataFrame()

        return all_prices.pct_change().dropna()

    def _optimize_sharpe(
        self,
        mu: np.ndarray,
        cov: np.ndarray,
        max_weight: float = 0.40,
    ) -> Tuple[np.ndarray, float]:
        """Sharpe Ratio를 최대화하는 포트폴리오 비중을 구한다.

        Args:
            mu: 자산별 기대수익률 벡터 (연율).
            cov: 공분산 행렬 (연율).
            max_weight: 개별 자산 비중 상한.

        Returns:
            (최적 비중 배열, 최대 Sharpe Ratio)
        """
        n = len(mu)
        rf = self.rf

        def neg_sharpe(w):
            port_ret = w @ mu
            port_vol = np.sqrt(w @ cov @ w)
            if port_vol < 1e-10:
                return 1e6
            return -(port_ret - rf) / port_vol

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        bounds = [(0.0, max_weight) for _ in range(n)]
        x0 = np.ones(n) / n

        result = minimize(
            neg_sharpe, x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-12},
        )

        if result.success:
            opt_w = result.x
            opt_sharpe = -result.fun
        else:
            # fallback: 균등 배분
            self.logger.warning("Optimizer did not converge. Using equal weights.")
            opt_w = np.ones(n) / n
            port_ret = opt_w @ mu
            port_vol = np.sqrt(opt_w @ cov @ opt_w)
            opt_sharpe = (port_ret - rf) / port_vol if port_vol > 0 else 0

        return opt_w, opt_sharpe

    # ─── 3. 메인 추천 파이프라인 ───────────────────────────────────────

    def recommend(
        self,
        lookback_years: int = 5,
        regime_override: Optional[str] = None,
    ) -> Dict:
        """매크로 국면을 진단하고 최적 포트폴리오를 추천한다.

        Args:
            lookback_years: 수익률 계산에 사용할 과거 데이터 연수.
            regime_override: 국면을 수동 지정 (None이면 자동 판단).

        Returns:
            Dict with keys:
                - regime: RegimeSnapshot
                - universe: 분석에 사용된 자산 목록
                - weights: {ticker: weight} 최적 배분
                - metrics: {expected_return, volatility, sharpe, ev}
                - efficient_frontier: List of (vol, ret) 포인트
        """
        # Step 1: 국면 진단
        snapshot = self.diagnose_regime()
        regime = regime_override if regime_override else snapshot.regime

        # Step 2: 자산 유니버스 선택
        universe = self.REGIME_UNIVERSE.get(regime, self.REGIME_UNIVERSE["Goldilocks"])
        max_w = self.REGIME_MAX_WEIGHT.get(regime, 0.35)

        # 스트레스가 높으면 방어적 자산 비중 상한 완화, 공격적 자산 상한 축소
        if snapshot.stress_score > 0.6:
            max_w = min(max_w, 0.30)

        # Step 3: 수익률 데이터 확보
        returns_df = self._fetch_returns(universe, lookback_years)
        if returns_df.empty or returns_df.shape[1] < 2:
            return {
                "error": "수익률 데이터가 부족합니다. 최소 2개 이상의 자산 데이터가 필요합니다.",
                "regime": snapshot,
            }

        available_tickers = returns_df.columns.tolist()

        # Step 4: 기대수익률 & 공분산
        mu = returns_df.mean().values * 252          # 연율화
        cov = returns_df.cov().values * 252          # 연율화

        # Step 5: 최적화
        opt_w, opt_sharpe = self._optimize_sharpe(mu, cov, max_weight=max_w)

        # 비중이 1% 미만인 자산은 제거하고 재정규화
        mask = opt_w >= 0.01
        final_tickers = [t for t, m in zip(available_tickers, mask) if m]
        final_weights = opt_w[mask]
        final_weights = final_weights / final_weights.sum()

        weights_dict = {t: round(float(w), 4) for t, w in zip(final_tickers, final_weights)}

        # 최종 포트폴리오 지표 계산
        # mu/cov는 전체 유니버스 기준이므로 최종 티커 기준으로 재계산
        final_idx = [available_tickers.index(t) for t in final_tickers]
        mu_final = mu[final_idx]
        cov_final = cov[np.ix_(final_idx, final_idx)]

        port_ret = float(final_weights @ mu_final)
        port_vol = float(np.sqrt(final_weights @ cov_final @ final_weights))
        port_sharpe = (port_ret - self.rf) / port_vol if port_vol > 0 else 0
        ev = port_ret - self.rf  # 기대값 (초과수익률)

        # Step 6: Efficient Frontier 포인트 생성
        ef_points = self._generate_efficient_frontier(mu, cov, max_w, n_points=30)

        # Step 7: 개별 자산 통계 (차트용)
        asset_stats = []
        for i, t in enumerate(available_tickers):
            asset_stats.append({
                "ticker": t,
                "expected_return": round(float(mu[i]) * 100, 2),
                "volatility": round(float(np.sqrt(cov[i, i])) * 100, 2),
                "weight": round(float(opt_w[i]) * 100, 2) if i < len(opt_w) else 0,
            })

        return {
            "regime": snapshot,
            "universe": available_tickers,
            "weights": weights_dict,
            "metrics": {
                "expected_return": round(port_ret * 100, 2),
                "volatility": round(port_vol * 100, 2),
                "sharpe": round(port_sharpe, 3),
                "ev": round(ev * 100, 2),  # EV as percentage
            },
            "asset_stats": asset_stats,
            "efficient_frontier": ef_points,
        }

    def _generate_efficient_frontier(
        self,
        mu: np.ndarray,
        cov: np.ndarray,
        max_weight: float,
        n_points: int = 30,
    ) -> List[Dict]:
        """Efficient Frontier 포인트들을 생성한다."""
        n = len(mu)
        target_returns = np.linspace(mu.min(), mu.max(), n_points)
        ef = []

        for target in target_returns:
            def port_vol(w):
                return np.sqrt(w @ cov @ w)

            constraints = [
                {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
                {"type": "eq", "fun": lambda w, t=target: w @ mu - t},
            ]
            bounds = [(0.0, max_weight)] * n
            x0 = np.ones(n) / n

            try:
                result = minimize(
                    port_vol, x0,
                    method="SLSQP",
                    bounds=bounds,
                    constraints=constraints,
                    options={"maxiter": 500, "ftol": 1e-10},
                )
                if result.success:
                    vol = float(np.sqrt(result.x @ cov @ result.x))
                    ret = float(result.x @ mu)
                    ef.append({"volatility": round(vol * 100, 2), "return": round(ret * 100, 2)})
            except Exception:
                continue

        return ef


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    optimizer = MacroOptimizer()

    result = optimizer.recommend()
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(f"\n=== 매크로 기반 최적 포트폴리오 ===")
        print(f"현재 국면: {result['regime'].regime}")
        print(f"국면 상세: {result['regime'].details}")
        print(f"\n최적 배분:")
        for t, w in result["weights"].items():
            print(f"  {t}: {w*100:.1f}%")
        print(f"\n기대수익률: {result['metrics']['expected_return']:.1f}%")
        print(f"변동성: {result['metrics']['volatility']:.1f}%")
        print(f"Sharpe: {result['metrics']['sharpe']:.3f}")
        print(f"EV (초과수익률): {result['metrics']['ev']:.1f}%")
