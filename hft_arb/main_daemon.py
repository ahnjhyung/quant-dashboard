"""
main_daemon.py - 24시간 HFT 차익거래 스나이퍼 데몬
===================================================
[사용법]
  python -m hft_arb.main_daemon

[데이터 플로우]
  Binance WS (펀딩비 + 오더북)
  Upbit WS (원화 오더북)          ──→  ev_engine (In-memory) ──→ executor (paper)
  Polymarket WS                                                        ↓
                                                               async_logger (Supabase)
               fail_safe ←── WS 재접속 실패 시 ───────────────────────┘

[SecurityAuditor] CRITICAL:
  - API Key는 config.py 경유
  - paper_trading=True 고정
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# 로깅 설정
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "daemon.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("hft_arb.daemon")

from hft_arb.ev_engine import EVEngine
from hft_arb.executor import ArbExecutor
from hft_arb.async_logger import AsyncLogger
from hft_arb.fail_safe import FailSafeManager
from hft_arb.market_discovery import MarketDiscovery
from hft_arb.ws_feeds.binance_ws import BinanceFundingFeed, BinanceSpotOrderbookFeed
from hft_arb.ws_feeds.upbit_ws import UpbitOrderbookFeed
from hft_arb.ws_feeds.bithumb_ws import BithumbOrderbookFeed
from hft_arb.ws_feeds.polymarket_feed import PolymarketFeed
from hft_arb.ws_feeds.cross_platform_feed import CrossPlatformFeed


# ──────────────────────────────────────────────────────────────
# 글로벌 상태 (In-memory)
# ──────────────────────────────────────────────────────────────
paper_positions: dict = {}


def _build_components() -> tuple:
    """모든 컴포넌트를 초기화하고 반환."""
    ev_engine = EVEngine(position_size_usd=10000.0)
    executor  = ArbExecutor(paper_trading=True, paper_positions=paper_positions)
    db_logger = AsyncLogger(table_name="arb_signals")
    fail_safe = FailSafeManager(paper_positions=paper_positions)
    return ev_engine, executor, db_logger, fail_safe


# ──────────────────────────────────────────────────────────────
# WebSocket 콜백 - 데이터 수신 → EV 계산 → 체결 → 비동기 기록
# ──────────────────────────────────────────────────────────────

async def on_funding_data(data: dict, ev_engine: EVEngine, executor: ArbExecutor, db_logger: AsyncLogger) -> None:
    """펀딩비 데이터 수신 콜백."""
    signal = ev_engine.calc_funding_arb(
        funding_rate=data["funding_rate"],
        symbol=data["symbol"],
    )
    if signal:
        pos_id = await executor.execute(signal)
        if pos_id:
            # fire-and-forget 비동기 기록 (체결 경로 블로킹 없음)
            asyncio.create_task(db_logger.log({
                "pos_id": pos_id,
                "strategy": signal.strategy,
                "symbol": signal.symbol,
                "ev_pct": signal.ev_pct,
                "details": signal.details,
            }))


async def on_spot_data(data: dict, ev_engine: EVEngine) -> None:
    """Binance 현물 오더북 수신 - 김치 프리미엄 계산용 캐시 업데이트."""
    ev_engine._binance_spot_cache[data["symbol"]] = data


async def on_upbit_data(data: dict, ev_engine: EVEngine, executor: ArbExecutor, db_logger: AsyncLogger) -> None:
    """Upbit 원화 오더북 수신 → 김치 프리미엄 및 Bithumb 크로스 차익 EV 계산."""
    symbol = data["market"].split("-")[1]
    
    # 캐시 업데이트
    ev_engine._upbit_cache[symbol] = data

    # 1. Binance vs Upbit Kimchi Premium 계산
    binance_cache = ev_engine._binance_spot_cache.get(f"{symbol}USDT")
    if binance_cache:
        signal = ev_engine.calc_kimchi_arb(
            p_krw=data["best_ask_krw"],
            p_usd=binance_cache["best_ask"],
            symbol=symbol,
            quantity=round(6000 / data["best_ask_krw"], 5),
        )
        if signal:
            pos_id = await executor.execute(signal)
            if pos_id:
                asyncio.create_task(db_logger.log({
                    "pos_id": pos_id,
                    "strategy": signal.strategy,
                    "symbol": signal.symbol,
                    "ev_pct": signal.ev_pct,
                    "details": signal.details,
                }))

    # 2. Upbit vs Bithumb Cross Arbitrage 계산
    bithumb_cache = getattr(ev_engine, "_bithumb_cache", {}).get(f"{symbol}_KRW")
    if bithumb_cache:
        cross_signal = ev_engine.calc_krw_cross_arb(
            p_upbit=data["best_ask_krw"],
            p_bithumb=bithumb_cache["best_ask_krw"],
            symbol=symbol,
            quantity=round(6000 / data["best_ask_krw"], 5),
        )
        if cross_signal:
            pos_id = await executor.execute(cross_signal)
            if pos_id:
                asyncio.create_task(db_logger.log({
                    "pos_id": pos_id,
                    "strategy": cross_signal.strategy,
                    "symbol": cross_signal.symbol,
                    "ev_pct": cross_signal.ev_pct,
                    "details": cross_signal.details,
                }))


async def on_bithumb_data(data: dict, ev_engine: EVEngine, executor: ArbExecutor, db_logger: AsyncLogger) -> None:
    """Bithumb 원화 오더북 수신 → Upbit 크로스 차익 EV 계산."""
    if not hasattr(ev_engine, "_bithumb_cache"):
        ev_engine._bithumb_cache = {}
        
    symbol = data["market"].split("_")[0]
    
    # 캐시 업데이트
    ev_engine._bithumb_cache[data["market"]] = data

    # Upbit vs Bithumb Cross Arbitrage 계산
    upbit_cache = ev_engine._upbit_cache.get(symbol)
    if upbit_cache:
        cross_signal = ev_engine.calc_krw_cross_arb(
            p_upbit=upbit_cache["best_ask_krw"],
            p_bithumb=data["best_ask_krw"],
            symbol=symbol,
            quantity=round(6000 / data["best_ask_krw"], 5),
        )
        if cross_signal:
            pos_id = await executor.execute(cross_signal)
            if pos_id:
                asyncio.create_task(db_logger.log({
                    "pos_id": pos_id,
                    "strategy": cross_signal.strategy,
                    "symbol": cross_signal.symbol,
                    "ev_pct": cross_signal.ev_pct,
                    "details": cross_signal.details,
                }))


async def on_polymarket_data(data: dict, ev_engine: EVEngine, executor: ArbExecutor, db_logger: AsyncLogger) -> None:
    """Polymarket 확률 데이터 수신 → 괴리 EV 계산."""
    signal = ev_engine.calc_polymarket_arb(
        condition_id=data["condition_id"],
        p_yes=data["p_yes"],
        p_no=data["p_no"],
    )
    if signal:
        pos_id = await executor.execute(signal)
        if pos_id:
            asyncio.create_task(db_logger.log({
                "pos_id": pos_id,
                "strategy": signal.strategy,
                "symbol": signal.symbol,
                "ev_pct": signal.ev_pct,
                "details": signal.details,
            }))


# ──────────────────────────────────────────────────────────────
# 데몬 메인 루프
# ──────────────────────────────────────────────────────────────

async def run_daemon() -> None:
    """24시간 데몬 메인 루프 (전 카테고리 자동 탐색 포함)."""
    logger.info("=" * 60)
    logger.info("HFT 차익거래 스나이퍼 봇 시작 (paper_trading=True)")
    logger.info("=" * 60)

    ev_engine, executor, db_logger, fail_safe = _build_components()
    discovery = MarketDiscovery(
        min_volume_usd=10_000.0,
        min_liquidity_usd=5_000.0,
        max_markets=200,
    )

    async def fail_safe_fn():
        await fail_safe.trigger("WebSocket 재접속 한계 초과")

    # ── 1단계: 시작 시 전 카테고리 마켓 자동 수집 ──
    logger.info("[Daemon] Polymarket 전 카테고리 마켓 탐색 중...")
    condition_ids, token_map = await discovery.fetch_all_markets()
    logger.info(f"[Daemon] {len(condition_ids)}개 마켓 발견 - WebSocket 구독 시작")

    # ── Polymarket WS 피드 ──
    poly_feed = PolymarketFeed(
        condition_ids=condition_ids,
        token_id_map=token_map,
        on_data=ev_engine.on_data_callback,
        fail_safe_fn=fail_safe_fn,
    )

    # 4. Cross-Platform Feed (Azuro) 추가
    azuro_feed = CrossPlatformFeed(
        on_data=ev_engine.on_data_callback,
        platform="azuro"
    )

    # 5. 실행기 생성 (ArbExecutor)
    executor = ArbExecutor(paper_trading=True, paper_positions=paper_positions)

    # ── 1시간 주기 마켓 목록 자동 갱신 ──
    async def on_market_update(new_ids: list[str], new_map: dict) -> None:
        """새 마켓 목록으로 Polymarket WS 피드 동적 갱신."""
        added   = set(new_ids) - set(poly_feed.condition_ids)
        removed = set(poly_feed.condition_ids) - set(new_ids)
        poly_feed.condition_ids = new_ids
        poly_feed.token_id_map  = new_map
        logger.info(
            f"[Daemon] 마켓 목록 갱신 - 총 {len(new_ids)}개 "
            f"(+{len(added)} 추가, -{len(removed)} 종료)"
        )

    # ── 모든 태스크 동시 실행 ──
    funding_feed = BinanceFundingFeed(
        symbol="btcusdt",
        on_data=lambda d: on_funding_data(d, ev_engine, executor, db_logger),
        fail_safe_fn=fail_safe_fn,
    )
    spot_feed = BinanceSpotOrderbookFeed(
        symbol="btcusdt",
        on_data=lambda d: on_spot_data(d, ev_engine),
        fail_safe_fn=fail_safe_fn,
    )
    upbit_feed = UpbitOrderbookFeed(
        market="KRW-BTC",
        on_data=lambda d: on_upbit_data(d, ev_engine, executor, db_logger),
        fail_safe_fn=fail_safe_fn,
    )
    bithumb_feed = BithumbOrderbookFeed(
        market="BTC_KRW",
        on_data=lambda d: on_bithumb_data(d, ev_engine, executor, db_logger),
        fail_safe_fn=fail_safe_fn,
    )

    tasks = [
        asyncio.create_task(funding_feed.connect(),                          name="funding_ws"),
        asyncio.create_task(spot_feed.connect(),                             name="spot_ws"),
        asyncio.create_task(upbit_feed.connect(),                            name="upbit_ws"),
        asyncio.create_task(bithumb_feed.connect(),                          name="bithumb_ws"),
        asyncio.create_task(db_logger.run(),                                 name="db_logger"),
        asyncio.create_task(
            discovery.refresh_loop(on_market_update, interval_sec=3600),     name="market_refresh"
        ),
        asyncio.create_task(azuro_feed.connect(),                            name="azuro_feed"),
    ]
    if poly_feed.condition_ids:
        tasks.append(asyncio.create_task(poly_feed.connect(),                name="poly_ws"))

    logger.info(f"[Daemon] 실행 태스크: {[t.get_name() for t in tasks]}")

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("[Daemon] 종료 신호 수신 - 정리 중...")
        for task in tasks:
            task.cancel()
        await fail_safe.trigger("데몬 정상 종료")
        logger.info("[Daemon] 종료 완료.")


def _handle_signal(sig, frame):
    logger.warning(f"[Daemon] OS 신호 수신: {sig}")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    asyncio.run(run_daemon())

