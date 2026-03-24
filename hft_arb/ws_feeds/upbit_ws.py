"""
upbit_ws.py — Upbit WebSocket 피드 (김치 프리미엄 계산용 원화 호가)
=======================================================================
[SecurityAuditor] CRITICAL 준수:
  - Upbit 공개 WebSocket은 인증 불필요 (구독 메시지만 전송)
  - 재접속: Exponential Backoff (최대 10회)
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Callable, Awaitable

import websockets

logger = logging.getLogger(__name__)

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"
MAX_RECONNECT = 10
RECONNECT_BASE_DELAY = 1.0


class UpbitOrderbookFeed:
    """
    Upbit 원화 오더북 WebSocket 피드.

    김치 프리미엄 차익 계산을 위해 Upbit KRW 마켓의 BTC 호가를 실시간 수신한다.

    Args:
        market: 거래쌍 (예: "KRW-BTC")
        on_data: 데이터 수신 시 호출할 async 콜백
        fail_safe_fn: 재접속 실패 시 호출할 fail-safe 함수
    """

    def __init__(
        self,
        market: str,
        on_data: Callable[[dict], Awaitable[None]],
        fail_safe_fn: Callable[[], Awaitable[None]] | None = None,
    ):
        self.market = market.upper()
        self.on_data = on_data
        self.fail_safe_fn = fail_safe_fn
        self._running = False

    def _subscribe_msg(self) -> str:
        """Upbit WebSocket 구독 메시지 생성."""
        return json.dumps([
            {"ticket": str(uuid.uuid4())},
            {"type": "orderbook", "codes": [self.market]},
            {"format": "SIMPLE"},
        ])

    async def connect(self) -> None:
        """WebSocket 연결 및 자동 재접속."""
        retries = 0
        self._running = True

        while self._running and retries <= MAX_RECONNECT:
            try:
                async with websockets.connect(
                    UPBIT_WS_URL
                ) as ws:
                    await ws.send(self._subscribe_msg())
                    logger.info(f"[UpbitFeed] Connected: {self.market}")
                    retries = 0

                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(raw)
                            units = data.get("obu", [])
                            if not units:
                                continue

                            best_ask = float(units[0].get("ap", 0))  # 최우선 매도호가
                            best_bid = float(units[0].get("bp", 0))  # 최우선 매수호가

                            if best_ask <= 0 or best_bid <= 0:
                                continue

                            await self.on_data({
                                "type": "upbit_orderbook",
                                "market": self.market,
                                "best_ask_krw": best_ask,
                                "best_bid_krw": best_bid,
                                "ts": time.time(),
                            })
                        except (ValueError, KeyError, IndexError) as e:
                            logger.warning(f"[UpbitFeed] Parse error: {e}")

            except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                retries += 1
                delay = RECONNECT_BASE_DELAY * (2 ** min(retries, 8))
                logger.error(
                    f"[UpbitFeed] Disconnected ({e}). "
                    f"Retry {retries}/{MAX_RECONNECT} in {delay:.1f}s"
                )
                if retries > MAX_RECONNECT:
                    logger.critical("[UpbitFeed] Max retries exceeded. Triggering fail-safe.")
                    if self.fail_safe_fn:
                        await self.fail_safe_fn()
                    self._running = False
                    return
                await asyncio.sleep(delay)

    def stop(self) -> None:
        self._running = False
