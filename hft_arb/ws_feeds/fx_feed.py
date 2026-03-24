"""
fx_feed.py — 실시간 USD/KRW 환율 피드
======================================
1분 주기로 환율을 갱신하여 ev_engine의 fx_rate_krw를 최신 상태로 유지.
데이터 소스: 네이버 금융 (무료, 인증 불필요)

[SecurityAuditor]
  - 네트워크 오류 시 마지막 유효 환율 유지 (0으로 fallback 금지)
  - 환율 범위 이탈 감지 (800~2000 외 값 무시)
"""
import asyncio
import logging
import time

import requests

logger = logging.getLogger(__name__)

# 환율 유효 범위 가드 (비정상 값 필터)
FX_MIN = 800.0
FX_MAX = 2000.0
REFRESH_INTERVAL_SEC = 60  # 1분 주기

# 네이버 금융 환율 API (CORS 없음, 안정적)
# 1차: 하나은행 고시환율 (안정적, 무료)
HANA_FX_API = "https://www.transfer.hanabank.com/contextRoot/cms/getCtfsRate.act"
# 2차 fallback: exchangerate-api (무료, API 키 불필요)
EXCHANGE_RATE_API = "https://open.er-api.com/v6/latest/USD"


def fetch_usd_krw() -> float | None:
    """
    USD/KRW 환율을 가져온다 (exchangerate-api 사용).

    Returns:
        현재 환율 또는 None (오류 시)
    """
    try:
        resp = requests.get(EXCHANGE_RATE_API, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        rate = float(data["rates"]["KRW"])

        if not (FX_MIN <= rate <= FX_MAX):
            logger.warning(f"[FXFeed] 환율 범위 이탈: {rate} — 무시")
            return None

        return rate

    except Exception as e:
        logger.error(f"[FXFeed] 환율 조회 실패: {e}")
        return None


class FXFeed:
    """
    USD/KRW 실시간 환율 피드.

    Args:
        ev_engine: EVEngine 인스턴스 (update_fx_rate 호출 대상)
        interval_sec: 갱신 주기 (기본 60초)
    """

    def __init__(self, ev_engine, interval_sec: int = REFRESH_INTERVAL_SEC):
        self.ev_engine = ev_engine
        self.interval_sec = interval_sec
        self._last_rate: float = 1445.0  # 초기 fallback
        self._last_updated: float = 0.0

    async def run(self) -> None:
        """비동기 환율 갱신 루프 (main_daemon 태스크로 실행)."""
        logger.info("[FXFeed] 환율 피드 시작")
        while True:
            rate = fetch_usd_krw()
            if rate is not None:
                self._last_rate = rate
                self._last_updated = time.time()
                self.ev_engine.update_fx_rate(rate)
                logger.info(f"[FXFeed] 환율 갱신: {rate:,.2f} KRW/USD")
            else:
                logger.warning(
                    f"[FXFeed] 갱신 실패, 이전 환율 유지: {self._last_rate:,.2f}"
                )
            await asyncio.sleep(self.interval_sec)
