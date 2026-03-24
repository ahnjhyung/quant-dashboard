"""
polymarket_feed.py — Polymarket CLOB WebSocket 피드
=====================================================
Polymarket은 공식 CLOB WebSocket API를 제공한다.
상호배타적 Yes/No 옵션의 합산 확률 괴리를 실시간 감지한다.

참고: https://docs.polymarket.com/#websocket

[SecurityAuditor] CRITICAL 준수:
  - API Key는 config.py 경유 (필요 시)
  - 재접속: Exponential Backoff
"""

import asyncio
import json
import logging
import time
from typing import Callable, Awaitable

import websockets

logger = logging.getLogger(__name__)

POLYMARKET_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
MAX_RECONNECT = 10
RECONNECT_BASE_DELAY = 1.0


class PolymarketFeed:
    """
    Polymarket 시장 WebSocket 피드.

    특정 condition_id의 Yes/No 토큰 가격을 구독하여
    합산 확률 괴리(Gap = 1.0 - P_yes - P_no)를 ev_engine에 전달한다.

    Args:
        condition_ids: 모니터링할 시장 condition ID 목록
        token_id_map: {condition_id: {"yes": token_id, "no": token_id}} 매핑
        on_data: 데이터 수신 시 호출할 async 콜백
        fail_safe_fn: 재접속 실패 시 호출할 fail-safe 함수
    """

    def __init__(
        self,
        condition_ids: list[str],
        token_id_map: dict[str, dict[str, str]],
        on_data: Callable[[dict], Awaitable[None]],
        fail_safe_fn: Callable[[], Awaitable[None]] | None = None,
    ):
        self.condition_ids = condition_ids
        self.token_id_map = token_id_map
        self.on_data = on_data
        self.fail_safe_fn = fail_safe_fn
        self._running = False
        # In-memory 가격 캐시: {condition_id: {"yes": price, "no": price}}
        self._price_cache: dict[str, dict[str, float]] = {}

    def _subscribe_msg(self) -> str:
        """시장 구독 메시지 생성."""
        assets = []
        for cid, tokens in self.token_id_map.items():
            assets.extend([tokens["yes"], tokens["no"]])
        return json.dumps({
            "type": "subscribe",
            "channel": "market",
            "market": self.condition_ids,
        })

    async def connect(self) -> None:
        """WebSocket 연결 및 자동 재접속."""
        retries = 0
        self._running = True

        while self._running and retries <= MAX_RECONNECT:
            try:
                async with websockets.connect(POLYMARKET_WS, ping_interval=20) as ws:
                    await ws.send(self._subscribe_msg())
                    logger.info(f"[Polymarket] Connected, monitoring {len(self.condition_ids)} markets")
                    retries = 0

                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            events = json.loads(raw)
                            if not isinstance(events, list):
                                events = [events]

                            for event in events:
                                await self._process_event(event)

                        except (ValueError, KeyError) as e:
                            logger.warning(f"[Polymarket] Parse error: {e}")

            except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                retries += 1
                delay = RECONNECT_BASE_DELAY * (2 ** min(retries, 8))
                logger.error(
                    f"[Polymarket] Disconnected ({e}). "
                    f"Retry {retries}/{MAX_RECONNECT} in {delay:.1f}s"
                )
                if retries > MAX_RECONNECT:
                    logger.critical("[Polymarket] Max retries. Triggering fail-safe.")
                    if self.fail_safe_fn:
                        await self.fail_safe_fn()
                    self._running = False
                    return
                await asyncio.sleep(delay)

    async def _process_event(self, event: dict) -> None:
        """수신된 이벤트로 가격 캐시 갱신 후 EV 콜백 호출."""
        event_type = event.get("event_type", "")
        if event_type not in ("price_change", "book"):
            return

        asset_id = event.get("asset_id", "")
        price_str = event.get("price") or event.get("best_ask")
        if price_str is None:
            return

        try:
            price = float(price_str)
        except ValueError:
            return

        # token_id → condition_id 역매핑 찾기
        for cid, tokens in self.token_id_map.items():
            side = None
            if tokens.get("yes") == asset_id:
                side = "yes"
            elif tokens.get("no") == asset_id:
                side = "no"

            if side:
                if cid not in self._price_cache:
                    self._price_cache[cid] = {}
                self._price_cache[cid][side] = price

                # Yes + No 양쪽 가격이 모두 있을 때만 EV 전달
                cache = self._price_cache.get(cid, {})
                if "yes" in cache and "no" in cache:
                    p_yes = cache["yes"]
                    p_no = cache["no"]
                    total = p_yes + p_no
                    gap = 1.0 - total  # 양수면 언더프라이싱

                    await self.on_data({
                        "type": "polymarket_gap",
                        "condition_id": cid,
                        "token_ids": self.token_id_map[cid],
                        "p_yes": p_yes,
                        "p_no": p_no,
                        "total": total,
                        "gap": gap,
                        "ts": time.time(),
                    })
                break

    def stop(self) -> None:
        self._running = False
