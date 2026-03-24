"""
phase2_multi_asset_backtest.py
================================
Phase 2: BTC + ETH + SOL 김치 차익 병렬 운영

핵심:
- 세 자산이 독립적으로 신호 생성 → 포트폴리오 EV 합산
- 자산 간 상관관계 분석 (높으면 의미 없음)
- 각 자산에 Kelly 적용
"""
import warnings
warnings.filterwarnings("ignore")
import requests, pandas as pd, numpy as np
from datetime import datetime

FEE_PCT        = 0.30
ENTRY_THRESH   = 0.30
EXIT_THRESH    = 0.05
MAX_HOLD_HOURS = 6
INITIAL_CAP    = 10_000_000
HALF_KELLY     = 0.5
MAX_ALLOC      = 0.40   # 자산당 최대 배분 (40%)
DAYS           = 400
BINANCE_API    = "https://api.binance.com/api/v3/klines"

ASSETS = {
    "BTC": {"symbol": "BTCUSDT", "kp_bull": 1.2, "kp_bear": 0.3, "kp_std": 2.0},
    "ETH": {"symbol": "ETHUSDT", "kp_bull": 1.5, "kp_bear": 0.4, "kp_std": 2.5},  # ETH는 변동성 큼
    "SOL": {"symbol": "SOLUSDT", "kp_bull": 2.0, "kp_bear": 0.5, "kp_std": 3.5},  # SOL은 더 큼
}


def fetch_hourly(symbol: str, days: int) -> pd.DataFrame:
    all_rows = []
    end_ms = int(datetime.now().timestamp() * 1000)
    rem = days * 24
    while rem > 0:
        fetch = min(rem, 1000)
        start_ms = end_ms - fetch * 3600 * 1000
        r = requests.get(BINANCE_API,
            params={"symbol": symbol, "interval": "1h",
                    "startTime": start_ms, "endTime": end_ms, "limit": fetch},
            verify=False, timeout=15)
        rows = r.json()
        if not rows or isinstance(rows, dict):
            break
        all_rows = rows + all_rows
        end_ms = start_ms - 1
        rem -= fetch
    df = pd.DataFrame(all_rows, columns=[
        "ts","open","high","low","close","vol","cts","qv","tr","tbb","tbq","ig"])
    df["dt"] = pd.to_datetime(df["ts"], unit="ms")
    df["close"] = df["close"].astype(float)
    df = df.drop_duplicates("dt").sort_values("dt").reset_index(drop=True)
    return df


def add_kp(df: pd.DataFrame, kp_bull: float, kp_bear: float, kp_std: float,
           seed_offset: int = 0) -> pd.DataFrame:
    np.random.seed(42 + seed_offset)
    prices = df["close"].values
    ma200h = pd.Series(prices).rolling(200, min_periods=1).mean().values
    regime = np.where(prices > ma200h, 1, -1)
    kp_mean = np.where(regime == 1, kp_bull / 24, kp_bear / 24)
    df = df.copy()
    df["kp"] = np.random.normal(kp_mean, kp_std / np.sqrt(24), len(df))
    df["regime"] = regime
    return df


def backtest_single(df: pd.DataFrame, order_pct: float = 0.10) -> dict:
    """단일 자산 백테스트 (수익 시계열 반환)"""
    capital = INITIAL_CAP
    returns_series = []
    trades = []
    pos = None

    for i, row in df.iterrows():
        kp = row["kp"]
        if pos is None and kp > ENTRY_THRESH:
            pos = {"hour": i, "entry_kp": kp, "size": capital * order_pct}
        elif pos is not None:
            held = i - pos["hour"]
            if kp < EXIT_THRESH or held >= MAX_HOLD_HOURS:
                net_pct = pos["entry_kp"] - kp - FEE_PCT
                pnl = pos["size"] * net_pct / 100
                capital = max(capital + pnl, 1)
                trades.append(net_pct)
                pos = None
        returns_series.append(capital)

    trades_arr = np.array(trades) if trades else np.array([0.0])
    return {
        "equity": np.array(returns_series),
        "trades": trades_arr,
        "win_rate": (trades_arr > 0).mean() * 100,
        "avg_ev": trades_arr.mean(),
        "n_trades": len(trades_arr),
        "final_cap": capital,
    }


def run_portfolio_backtest(asset_dfs: dict) -> dict:
    """
    3자산 포트폴리오 백테스트.
    각 자산별 신호를 독립적으로 생성하고 자본을 분할 배분.
    자산당 최대 40% (Half-Kelly 기준)
    """
    # 공통 시간축으로 정렬 (인덱스 일치)
    min_len = min(len(df) for df in asset_dfs.values())

    capital = INITIAL_CAP
    equity = [capital]
    all_trades = []

    # 자산당 30% 배분 (3자산 × 30% = 90%, 10% 예비)
    alloc_per_asset = min(MAX_ALLOC, 0.30)

    positions = {k: None for k in asset_dfs}
    asset_trades = {k: [] for k in asset_dfs}

    for i in range(min_len):
        for asset, df in asset_dfs.items():
            if i >= len(df):
                continue
            row = df.iloc[i]
            kp = row["kp"]
            pos = positions[asset]

            if pos is None and kp > ENTRY_THRESH:
                positions[asset] = {
                    "hour": i, "entry_kp": kp,
                    "size": capital * alloc_per_asset
                }
            elif pos is not None:
                held = i - pos["hour"]
                if kp < EXIT_THRESH or held >= MAX_HOLD_HOURS:
                    net_pct = pos["entry_kp"] - kp - FEE_PCT
                    pnl = pos["size"] * net_pct / 100
                    capital = max(capital + pnl, 1)
                    asset_trades[asset].append(net_pct)
                    all_trades.append({"asset": asset, "net_pct": net_pct})
                    positions[asset] = None

        equity.append(capital)

    eq = np.array(equity)
    years = min_len / (24 * 365)
    all_trades_df = pd.DataFrame(all_trades) if all_trades else pd.DataFrame()

    total_ret = (capital - INITIAL_CAP) / INITIAL_CAP * 100
    cagr = ((capital / INITIAL_CAP) ** (1 / max(years, 0.01)) - 1) * 100
    mdd = ((pd.Series(eq) - pd.Series(eq).cummax()) / pd.Series(eq).cummax() * 100).min()

    return {
        "cagr": cagr, "mdd": mdd, "total_ret": total_ret,
        "n_trades": len(all_trades_df),
        "win_rate": (all_trades_df["net_pct"] > 0).mean() * 100 if len(all_trades_df) else 0,
        "avg_ev": all_trades_df["net_pct"].mean() if len(all_trades_df) else 0,
        "years": years, "final_cap": capital,
        "asset_trades": asset_trades,
        "all_trades": all_trades_df,
    }


if __name__ == "__main__":
    print("=" * 62)
    print("  Phase 2: BTC + ETH + SOL 김치 차익 병렬 운영")
    print(f"  기간: 최근 {DAYS}일 시간봉")
    print("=" * 62)

    # 데이터 수집
    asset_dfs = {}
    for name, cfg in ASSETS.items():
        print(f"[DATA] {name} ({cfg['symbol']}) 수집 중...")
        df = fetch_hourly(cfg["symbol"], DAYS)
        df = add_kp(df, cfg["kp_bull"], cfg["kp_bear"], cfg["kp_std"],
                    seed_offset=list(ASSETS.keys()).index(name))
        asset_dfs[name] = df
        print(f"  -> {len(df):,}시간 | KP 평균={df['kp'].mean():.3f}% "
              f"| >0.3% 비율={( df['kp'] > 0.30).mean()*100:.1f}%")

    # 상관관계 분석
    print("\n[상관관계 분석 -- 이 값이 낮을수록 분산 효과 큼]")
    kp_df = pd.DataFrame({k: asset_dfs[k]["kp"].values[:min(len(v) for v in asset_dfs.values())]
                          for k, v in asset_dfs.items()})
    corr = kp_df.corr()
    print(corr.to_string())

    # 단일 자산 개별 결과
    print("\n[개별 자산 백테스트 (30% 배분 고정)]")
    print(f"  {'자산':>5} | {'CAGR':>7} | {'MDD':>6} | {'거래수':>6} | {'승률':>6} | {'EV':>8}")
    print("  " + "-" * 50)
    for name, df in asset_dfs.items():
        r = backtest_single(df, order_pct=0.30)
        years = len(df) / (24 * 365)
        cagr_s = ((r["final_cap"] / INITIAL_CAP) ** (1 / max(years, 0.01)) - 1) * 100
        eq_s = r["equity"]
        mdd_s = ((pd.Series(eq_s) - pd.Series(eq_s).cummax()) / pd.Series(eq_s).cummax() * 100).min()
        print(f"  {name:>5} | {cagr_s:>+6.1f}% | {mdd_s:>5.1f}% | {r['n_trades']:>6} | "
              f"{r['win_rate']:>5.1f}% | {r['avg_ev']:>+7.4f}%")

    # 포트폴리오 결합
    print("\n[Phase 2 포트폴리오 통합 결과 (3자산 × 30%)]")
    port = run_portfolio_backtest(asset_dfs)
    sep = "=" * 62
    print(f"\n{sep}")
    print(f"  Phase 2: BTC+ETH+SOL 포트폴리오 결과")
    print(sep)
    print(f"  기간      : {port['years']:.1f}년")
    print(f"  초기자본  : {INITIAL_CAP:,}원")
    print(f"  최종자본  : {port['final_cap']:,.0f}원")
    print(f"  CAGR      : {port['cagr']:+.1f}% / 년")
    print(f"  MDD       : {port['mdd']:.2f}%")
    print(f"  총 거래수 : {port['n_trades']:,}회")
    print(f"  승   률   : {port['win_rate']:.1f}%")
    print(f"  평균 EV   : {port['avg_ev']:+.4f}% / 거래")
    print(sep)

    print("\n  [자산별 거래 수]")
    for k, t in port["asset_trades"].items():
        print(f"    {k}: {len(t)}회")

    print("\n  [기존 대비 개선]")
    print(f"  일봉 단일 BTC  : CAGR +22.8%  MDD -1.3%")
    print(f"  Phase 2 포트폴 : CAGR {port['cagr']:+.1f}%  MDD {port['mdd']:.1f}%")
    improvement = port["cagr"] - 22.8
    print(f"  개선 폭       : {improvement:+.1f}%p")
