"""
cross_platform_feed.py — Base 체인(Azuro/Limitless) GraphQL 데이터 피드
===================================================================
[SoftwareEngineer]
  - Subgraph/GraphQL을 정기적으로 폴링하여 가격 데이터를 수신한다.
  - Polymarket과 동일한 이벤트의 가격을 비교하기 위해 Mapper와 협력한다.
"""

import asyncio
import logging
import time
from typing import Callable, Awaitable, List

import aiohttp
from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport

logger = logging.getLogger(__name__)

# Azuro Protocol v3 (Base) - 검증된 엔드포인트
AZURO_BASE_GRAPHQL = "https://thegraph.onchainfeed.org/subgraphs/name/azuro-protocol/azuro-api-base-v3"
POLL_INTERVAL = 5.0  # 초 (HFT라기보다는 스캐너에 가깝지만 괴리 탐색에 충분)

class CrossPlatformFeed:
    """
    Base 체인 예측 시장(GraphQL 기반) 데이터 피드.
    
    Args:
        on_data: 데이터 수신 시 호출할 async 콜백
        platform: "azuro" or "limitless"
    """
    
    def __init__(self, on_data: Callable[[dict], Awaitable[None]], platform: str = "azuro"):
        self.on_data = on_data
        self.platform = platform
        self.url = AZURO_BASE_GRAPHQL if platform == "azuro" else None
        self._running = False
        
        if not self.url and platform == "azuro":
             logger.error("[CrossFeed] Azuro URL is missing")

    async def connect(self) -> None:
        """폴링 루프 시작."""
        if not self.url:
            logger.warning(f"[CrossFeed] {self.platform} URL이 설정되지 않아 작동하지 않습니다.")
            return

        self._running = True
        transport = AIOHTTPTransport(url=self.url)
        
        async with Client(transport=transport, fetch_schema_from_transport=False) as session:
            logger.info(f"[CrossFeed] Connected to {self.platform} GraphQL")
            
            while self._running:
                try:
                    # 마켓 데이터 쿼리 (Azuro 기준 예시)
                    # 실제 쿼리는 플랫폼별 스키마에 따라 달라집니다.
                    query = gql("""
                        query GetMarkets {
                            games(first: 20, where: { status: Created }, orderBy: startsAt) {
                                id
                                title
                                conditions {
                                    id
                                    outcomes {
                                        outcomeId
                                        currentOdds
                                    }
                                }
                            }
                        }
                    """)
                    
                    result = await session.execute(query)
                    await self._process_result(result)
                    
                except Exception as e:
                    logger.error(f"[CrossFeed] {self.platform} query error: {e}")
                
                await asyncio.sleep(POLL_INTERVAL)

    async def _process_result(self, result: dict) -> None:
        """결과 파싱 및 콜백 전송."""
        # Azuro v3 스키마 기준: games -> conditions -> outcomes
        games = result.get("games", [])
        for game in games:
            game_id = game["id"]
            title = game["title"]
            conditions = game.get("conditions", [])
            
            for cond in conditions:
                outcomes = cond.get("outcomes", [])
                
                # 배당률(Odds)을 확률(Probability)로 변환 (P = 1/Odds)
                prices = {}
                for oc in outcomes:
                    oid = oc["outcomeId"]
                    odds = float(oc["currentOdds"])
                    if odds > 0:
                        prices[oid] = 1.0 / odds
                
                if prices:
                    await self.on_data({
                        "type": "external_price",
                        "platform": self.platform,
                        "external_id": f"{game_id}_{cond['id']}",
                        "title": title,
                        "prices": prices,
                        "ts": time.time(),
                    })

    def stop(self) -> None:
        self._running = False
