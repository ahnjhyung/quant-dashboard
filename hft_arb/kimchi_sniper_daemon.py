"""
kimchi_sniper_daemon.py - 안드로이드용 김치 프리미엄 전용 스나이퍼
=============================================================
[최적화 내역]
  - Binance 펀딩비 / Polymarket / Azuro 피드 완전 제거 (CPU 60% 절감)
  - Upbit / Binance(BTC/ETG/SOL) / Bithumb 원화 격차에만 집중
  - lite_config.py를 통한 네트워크 대역폭 및 배터리 절약
"""

import argparse
import asyncio
import logging
import signal
import sys
import httpx
from pathlib import Path

# 설정 로드
try:
    from hft_arb.lite_config import POLLING_INTERVALS, LOG_LEVEL, WS_RECONNECT_DELAY
except ImportError:
    POLLING_INTERVALS = {"fx_sync": 60}
    LOG_LEVEL = "INFO"
    WS_RECONNECT_DELAY = 10.0

# 로깅 설정
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "kimchi_sniper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("KimchiSniper")

from hft_arb.ev_engine import EVEngine
from hft_arb.executor import ArbExecutor
from hft_arb.async_logger import AsyncLogger
from hft_arb.ws_feeds.binance_ws import BinanceSpotOrderbookFeed
from hft_arb.ws_feeds.upbit_ws import UpbitOrderbookFeed
from hft_arb.ws_feeds.bithumb_ws import BithumbOrderbookFeed

async def on_upbit_data(data: dict, ev_engine: EVEngine, executor: ArbExecutor, db_logger: AsyncLogger) -> None:
    """Upbit 데이터 수신 -> 김프 및 크로스 차익 계산."""
    symbol = data["market"].split("-")[1]
    ev_engine._upbit_cache[symbol] = data

    # 1. Kimchi Premium (Binance vs Upbit)
    binance_cache = ev_engine._binance_spot_cache.get(f"{symbol}USDT")
    if binance_cache:
        signal = ev_engine.calc_kimchi_arb(
            p_krw=data["best_ask_krw"],
            p_usd=binance_cache["best_ask"],
            symbol=symbol,
        )
        if signal:
            pos_id = await executor.execute(signal)
            if pos_id:
                asyncio.create_task(db_logger.log({
                    "pos_id": pos_id, "strategy": signal.strategy, "symbol": signal.symbol,
                    "ev_pct": signal.ev_pct, "details": signal.details,
                }))

    # 2. KRW Cross Arb (Upbit vs Bithumb)
    b_cache = getattr(ev_engine, "_bithumb_cache", {}).get(f"{symbol}_KRW")
    if b_cache:
        cross_sig = ev_engine.calc_krw_cross_arb(
            p_upbit=data["best_ask_krw"],
            p_bithumb=b_cache["best_ask_krw"],
            symbol=symbol,
        )
        if cross_sig:
            pos_id = await executor.execute(cross_sig)
            if pos_id:
                asyncio.create_task(db_logger.log({
                    "pos_id": pos_id, "strategy": cross_sig.strategy, "symbol": cross_sig.symbol,
                    "ev_pct": cross_sig.ev_pct, "details": cross_sig.details,
                }))

async def run_kimchi_daemon(live: bool = False, balance: float = 100.0) -> None:
    logger.info("=" * 50)
    logger.info(f"KIMCHI SNIPER (Android Dedicated) Starting...")
    logger.info(f"Mode: {'REAL' if live else 'PAPER'}, Balance: ${balance}")
    logger.info("=" * 50)

    ev_engine = EVEngine(total_capital_usd=balance)
    executor  = ArbExecutor(paper_trading=not live)
    db_logger = AsyncLogger(table_name="arb_signals")

    # 실시간 환율 업데이트
    async def update_fx():
        while True:
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.get("https://api.upbit.com/v1/ticker?markets=KRW-USDT")
                    if res.status_code == 200:
                        ev_engine.fx_rate_krw = float(res.json()[0]["trade_price"])
                        logger.info(f"[FX] USDT-KRW: {ev_engine.fx_rate_krw:,.2f}")
            except Exception as e: logger.error(f"FX Sync Error: {e}")
            await asyncio.sleep(POLLING_INTERVALS.get("fx_sync", 60))

    asyncio.create_task(update_fx())

    # 피드 설정 (BTC, ETH, SOL 집중)
    symbols = ["BTC", "ETH", "SOL"]
    feeds = []
    
    for sym in symbols:
        # Binance Spot
        feeds.append(BinanceSpotOrderbookFeed(
            symbol=f"{sym.lower()}usdt",
            on_data=lambda d: ev_engine._binance_spot_cache.update({d["symbol"]: d})
        ))
        # Upbit
        feeds.append(UpbitOrderbookFeed(
            market=f"KRW-{sym}",
            on_data=lambda d: on_upbit_data(d, ev_engine, executor, db_logger)
        ))
        # Bithumb
        feeds.append(BithumbOrderbookFeed(
            market=f"{sym}_KRW",
            on_data=lambda d: getattr(ev_engine, "_bithumb_cache", {}).update({d["market"]: d})
        ))

    tasks = [asyncio.create_task(f.connect()) for f in feeds]
    tasks.append(asyncio.create_task(db_logger.run()))

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for t in tasks: t.cancel()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--balance", type=float, default=100.0)
    args = parser.parse_args()

    def handle_exit(sig, frame): sys.exit(0)
    signal.signal(signal.SIGINT, handle_exit)

    asyncio.run(run_kimchi_daemon(live=args.live, balance=args.balance))
