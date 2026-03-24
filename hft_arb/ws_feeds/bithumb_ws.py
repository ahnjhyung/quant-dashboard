"""
bithumb_ws.py — Bithumb WebSocket 피드 (김치 프리미엄 계산용 원화 호가)
=======================================================================
[SecurityAuditor] CRITICAL 준수:
  - Bithumb 공개 WebSocket은 인증 불필요
  - 재접속: Exponential Backoff (최대 10회)
"""

import asyncio
import json
import logging
import time
from typing import Callable, Awaitable

import websockets

logger = logging.getLogger(__name__)

BITHUMB_WS_URL = "wss://pubwss.bithumb.com/pub/ws"
MAX_RECONNECT = 10
RECONNECT_BASE_DELAY = 1.0


class BithumbOrderbookFeed:
    """
    Bithumb 원화 오더북 WebSocket 피드.

    김치 프리미엄 차익 계산을 위해 Bithumb KRW 마켓의 BTC 호가를 실시간 수신한다.

    Args:
        market: 거래쌍 (예: "BTC_KRW")
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
        """Bithumb WebSocket 구독 메시지 생성."""
        return json.dumps({
            "type": "orderbookdepth",
            "symbols": [self.market]
        })

    async def connect(self) -> None:
        """WebSocket 연결 및 자동 재접속."""
        retries = 0
        self._running = True

        while self._running and retries <= MAX_RECONNECT:
            try:
                async with websockets.connect(
                    BITHUMB_WS_URL
                ) as ws:
                    await ws.send(self._subscribe_msg())
                    logger.info(f"[BithumbFeed] Connected: {self.market}")
                    retries = 0

                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(raw)
                            
                            # 응답 메시지 확인
                            if data.get("status") == "0000":
                                continue
                                
                            content = data.get("content", {})
                            list_data = content.get("list", [])
                            if not list_data:
                                continue

                            asks = sorted([item for item in list_data if item["orderType"] == "ask"], key=lambda x: float(x["price"]))
                            bids = sorted([item for item in list_data if item["orderType"] == "bid"], key=lambda x: float(x["price"]), reverse=True)

                            if not asks or not bids:
                                continue

                            best_ask = float(asks[0]["price"])  # 최우선 매도호가
                            best_bid = float(bids[0]["price"])  # 최우선 매수호가

                            if best_ask <= 0 or best_bid <= 0:
                                continue

                            await self.on_data({
                                "type": "bithumb_orderbook",
                                "market": self.market,
                                "best_ask_krw": best_ask,
                                "best_bid_krw": best_bid,
                                "ts": time.time(),
                            })
                        except (ValueError, KeyError, IndexError) as e:
                            logger.warning(f"[BithumbFeed] Parse error: {e}")

            except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                retries += 1
                delay = RECONNECT_BASE_DELAY * (2 ** min(retries, 8))
                logger.error(
                    f"[BithumbFeed] Disconnected ({e}). "
                    f"Retry {retries}/{MAX_RECONNECT} in {delay:.1f}s"
                )
                if retries > MAX_RECONNECT:
                    logger.critical("[BithumbFeed] Max retries exceeded. Triggering fail-safe.")
                    if self.fail_safe_fn:
                        await self.fail_safe_fn()
                    self._running = False
                    return
                await asyncio.sleep(delay)

    def stop(self) -> None:
        self._running = False
