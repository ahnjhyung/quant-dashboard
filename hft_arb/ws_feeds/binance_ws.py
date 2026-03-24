"""
binance_ws.py — Binance WebSocket 피드 (선물 펀딩비 + 현물 오더북)
=================================================================
[SecurityAuditor] CRITICAL 준수:
  - API Key를 URL에 포함하지 않음 (WebSocket 공개 스트림 사용)
  - 인증이 필요한 경우 config.py를 통해서만 로드
  - 재접속: Exponential Backoff (최대 10회)
"""

import asyncio
import json
import logging
import time
from typing import Callable, Awaitable

import websockets

logger = logging.getLogger(__name__)

BINANCE_FUTURE_WS = "wss://fstream.binance.com/ws"
BINANCE_SPOT_WS = "wss://stream.binance.com:9443/ws"

MAX_RECONNECT = 10
RECONNECT_BASE_DELAY = 1.0  # seconds (exponential backoff base)


class BinanceFundingFeed:
    """
    Binance 선물 펀딩비 WebSocket 피드.

    실시간 markPrice 스트림을 통해 8시간 펀딩비(fundingRate)를 수신한다.
    데이터는 콜백(on_data)으로 ev_engine에 전달된다.

    Args:
        symbol: 거래쌍 (예: "btcusdt")
        on_data: 데이터 수신 시 호출할 async 콜백 함수
        fail_safe_fn: WebSocket 재접속 실패 시 호출할 fail-safe 함수
    """

    def __init__(
        self,
        symbol: str,
        on_data: Callable[[dict], Awaitable[None]],
        fail_safe_fn: Callable[[], Awaitable[None]] | None = None,
    ):
        self.symbol = symbol.lower()
        self.on_data = on_data
        self.fail_safe_fn = fail_safe_fn
        self._running = False

    async def connect(self) -> None:
        """WebSocket 연결 시작 (자동 재접속 포함)."""
        stream = f"{BINANCE_FUTURE_WS}/{self.symbol}@markPrice"
        retries = 0
        self._running = True

        while self._running and retries <= MAX_RECONNECT:
            try:
                async with websockets.connect(stream, ping_interval=20) as ws:
                    logger.info(f"[BinanceFunding] Connected: {stream}")
                    retries = 0  # 연결 성공 시 재시도 카운터 초기화
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(raw)
                            # [SecurityAuditor] NaN 방어: fundingRate 유효성 검사
                            fr = data.get("r")
                            if fr is None:
                                continue
                            fr_float = float(fr)
                            if fr_float != fr_float:  # NaN 체크
                                logger.warning("[BinanceFunding] NaN fundingRate, skip")
                                continue
                            await self.on_data({
                                "type": "funding_rate",
                                "symbol": self.symbol.upper(),
                                "funding_rate": fr_float,
                                "mark_price": float(data.get("p", 0)),
                                "next_funding_time": data.get("T"),
                                "ts": time.time(),
                            })
                        except (ValueError, KeyError) as e:
                            logger.warning(f"[BinanceFunding] Parse error: {e}")

            except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                retries += 1
                delay = RECONNECT_BASE_DELAY * (2 ** min(retries, 8))
                logger.error(
                    f"[BinanceFunding] Disconnected ({e}). "
                    f"Retry {retries}/{MAX_RECONNECT} in {delay:.1f}s"
                )

                if retries > MAX_RECONNECT:
                    logger.critical("[BinanceFunding] Max retries exceeded. Triggering fail-safe.")
                    if self.fail_safe_fn:
                        await self.fail_safe_fn()
                    self._running = False
                    return

                await asyncio.sleep(delay)

    def stop(self) -> None:
        """피드 중지."""
        self._running = False


class BinanceSpotOrderbookFeed:
    """
    Binance 현물 오더북 WebSocket 피드.

    김치 프리미엄 차익 계산을 위해 Binance BTC 현물 최우선 매수/매도 호가를 수신한다.

    Args:
        symbol: 거래쌍 (예: "btcusdt")
        on_data: 데이터 수신 시 호출할 async 콜백
        fail_safe_fn: 재접속 실패 시 호출할 fail-safe 함수
    """

    def __init__(
        self,
        symbol: str,
        on_data: Callable[[dict], Awaitable[None]],
        fail_safe_fn: Callable[[], Awaitable[None]] | None = None,
    ):
        self.symbol = symbol.lower()
        self.on_data = on_data
        self.fail_safe_fn = fail_safe_fn
        self._running = False

    async def connect(self) -> None:
        """WebSocket 연결 시작 (자동 재접속 포함)."""
        stream = f"{BINANCE_SPOT_WS}/{self.symbol}@bookTicker"
        retries = 0
        self._running = True

        while self._running and retries <= MAX_RECONNECT:
            try:
                async with websockets.connect(stream, ping_interval=20) as ws:
                    logger.info(f"[BinanceSpot] Connected: {stream}")
                    retries = 0
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(raw)
                            best_bid = float(data.get("b", 0))
                            best_ask = float(data.get("a", 0))
                            if best_bid <= 0 or best_ask <= 0:
                                continue
                            await self.on_data({
                                "type": "spot_orderbook",
                                "symbol": self.symbol.upper(),
                                "best_bid": best_bid,
                                "best_ask": best_ask,
                                "ts": time.time(),
                            })
                        except (ValueError, KeyError) as e:
                            logger.warning(f"[BinanceSpot] Parse error: {e}")

            except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                retries += 1
                delay = RECONNECT_BASE_DELAY * (2 ** min(retries, 8))
                logger.error(
                    f"[BinanceSpot] Disconnected ({e}). "
                    f"Retry {retries}/{MAX_RECONNECT} in {delay:.1f}s"
                )
                if retries > MAX_RECONNECT:
                    logger.critical("[BinanceSpot] Max retries exceeded. Triggering fail-safe.")
                    if self.fail_safe_fn:
                        await self.fail_safe_fn()
                    self._running = False
                    return
                await asyncio.sleep(delay)

    def stop(self) -> None:
        self._running = False
