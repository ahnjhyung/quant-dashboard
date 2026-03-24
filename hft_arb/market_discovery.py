"""
market_discovery.py - Polymarket 전 카테고리 활성 마켓 자동 탐색
=================================================================
Polymarket Gamma Markets API를 통해 모든 카테고리의 활성 마켓을
자동으로 수집하고, WebSocket 구독에 필요한 condition_id + token_id_map을
동적으로 생성한다.

[SecurityAuditor] MEDIUM:
  - API 응답값 타입/범위 검증 필수
  - Rate limit 준수 (요청 간 0.2초 딜레이)
"""

import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Polymarket 공개 API (인증 불필요)
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE  = "https://clob.polymarket.com"

RATE_LIMIT_DELAY = 0.2  # 초 (요청 간 최소 간격)
PAGE_SIZE = 100           # 한 번에 가져올 마켓 수 (최대 100)


class MarketDiscovery:
    """
    Polymarket 전 카테고리 활성 마켓 자동 탐색기.

    Gamma API를 통해 YES/NO 바이너리 마켓 전체를 페이지네이션으로 수집한다.
    수집된 마켓은 WebSocket 피드가 구독할 수 있는 형태로 반환된다.

    Args:
        min_volume_usd: 최소 유동성 필터 (USD). 너무 얇은 마켓 제외.
        min_liquidity_usd: 최소 유동성 $. 슬리피지 방어.
        max_markets: 동시 모니터링할 최대 마켓 수 (WebSocket 연결 부하 방어)
    """

    def __init__(
        self,
        min_volume_usd: float = 10_000.0,
        min_liquidity_usd: float = 5_000.0,
        max_markets: int = 200,
    ):
        self.min_volume_usd = min_volume_usd
        self.min_liquidity_usd = min_liquidity_usd
        self.max_markets = max_markets

    async def fetch_all_markets(self) -> tuple[list[str], dict[str, dict[str, str]]]:
        """
        모든 활성 바이너리 마켓을 수집하여 반환.

        Returns:
            (condition_ids, token_id_map) 튜플
            - condition_ids: WS 구독용 condition ID 목록
            - token_id_map: {condition_id: {"yes": token_id, "no": token_id}}
        """
        logger.info("[Discovery] 전 카테고리 활성 마켓 탐색 시작...")
        markets = await self._paginate_markets()
        condition_ids, token_map = self._parse_markets(markets)
        logger.info(
            f"[Discovery] 완료 - 총 {len(condition_ids)}개 마켓 발견 "
            f"(필터: volume≥${self.min_volume_usd:,.0f}, liq≥${self.min_liquidity_usd:,.0f})"
        )
        return condition_ids, token_map

    async def _paginate_markets(self) -> list[dict]:
        """Gamma API 페이지네이션으로 모든 마켓 수집."""
        all_markets: list[dict] = []
        offset = 0

        async with httpx.AsyncClient(timeout=10.0) as client:
            while len(all_markets) < self.max_markets:
                try:
                    resp = await client.get(
                        f"{GAMMA_API_BASE}/markets",
                        params={
                            "active": "true",
                            "closed": "false",
                            "archived": "false",
                            "limit": PAGE_SIZE,
                            "offset": offset,
                        },
                    )
                    resp.raise_for_status()
                    page: list[dict] = resp.json()

                    if not page:
                        break  # 더 이상 마켓 없음

                    all_markets.extend(page)
                    logger.debug(f"[Discovery] 페이지 수집: offset={offset}, +{len(page)}건")

                    if len(page) < PAGE_SIZE:
                        break  # 마지막 페이지

                    offset += PAGE_SIZE
                    await asyncio.sleep(RATE_LIMIT_DELAY)

                except httpx.HTTPStatusError as e:
                    logger.error(f"[Discovery] API 오류: {e.response.status_code}")
                    break
                except (httpx.TimeoutException, httpx.RequestError) as e:
                    logger.error(f"[Discovery] 네트워크 오류: {e}")
                    break

        return all_markets

    def _parse_markets(
        self, markets: list[dict]
    ) -> tuple[list[str], dict[str, dict[str, str]]]:
        """
        수집된 마켓 데이터에서 condition_id + token 매핑 추출.
        유동성 필터 적용 후 반환.
        """
        condition_ids: list[str] = []
        token_map: dict[str, dict[str, str]] = {}
        skipped = 0

        for m in markets:
            try:
                # 바이너리 마켓만 처리 (outcomes = ["Yes", "No"])
                outcomes = m.get("outcomes", [])
                if isinstance(outcomes, str):
                    import json
                    outcomes = json.loads(outcomes)
                if len(outcomes) != 2:
                    skipped += 1
                    continue

                # 볼륨 필터
                volume = float(m.get("volumeNum", 0) or 0)
                liquidity = float(m.get("liquidityNum", 0) or 0)
                if volume < self.min_volume_usd or liquidity < self.min_liquidity_usd:
                    skipped += 1
                    continue

                condition_id: str = m.get("conditionId", "")
                if not condition_id:
                    skipped += 1
                    continue

                # clobTokenIds: ["yes_token_id", "no_token_id"]
                clob_ids = m.get("clobTokenIds", [])
                if isinstance(clob_ids, str):
                    import json
                    clob_ids = json.loads(clob_ids)
                if len(clob_ids) < 2:
                    skipped += 1
                    continue

                yes_token = clob_ids[0]
                no_token  = clob_ids[1]

                condition_ids.append(condition_id)
                token_map[condition_id] = {
                    "yes": yes_token,
                    "no": no_token,
                    "question": (m.get("question", "") or "")[:80],
                    "category": m.get("category", "unknown"),
                    "volume_usd": volume,
                    "liquidity_usd": liquidity,
                }

                if len(condition_ids) >= self.max_markets:
                    break

            except (ValueError, KeyError, TypeError) as e:
                logger.warning(f"[Discovery] 마켓 파싱 오류: {e}")
                skipped += 1

        logger.info(
            f"[Discovery] 파싱 결과 - 채택: {len(condition_ids)}, 제외: {skipped}"
        )
        return condition_ids, token_map

    async def refresh_loop(
        self,
        on_update: callable,
        interval_sec: int = 3600,
    ) -> None:
        """
        주기적으로 마켓 목록을 갱신하는 루프.

        새 마켓이 생기거나 기존 마켓이 종료될 때 자동 반영.

        Args:
            on_update: (condition_ids, token_map) 수신 콜백
            interval_sec: 갱신 주기 (기본 1시간)
        """
        while True:
            try:
                ids, token_map = await self.fetch_all_markets()
                await on_update(ids, token_map)
                logger.info(f"[Discovery] 마켓 목록 갱신 완료 ({len(ids)}건). 다음 갱신: {interval_sec//60}분 후")
            except Exception as e:
                logger.error(f"[Discovery] 갱신 실패: {e}")

            await asyncio.sleep(interval_sec)
