"""
krw_cross_scanner.py — 업비트↔빗썸 실시간 스프레드 스캐너
==========================================================
분 단위로 업비트와 빗썸 가격을 동시 조회하여 스프레드가 임계점(0.60%)을
초과하면 EV 신호를 발생시킨다.

[전략 원리]
  - 양쪽 거래소에 코인+KRW를 미리 예치
  - 스프레드 감지 시 동시 주문 (매수/매도)
  - 코인 전송 불필요 → 네트워크 수수료 $0
  - 실질 수수료: 업비트 0.05% + 빗썸 0.25% + 슬리피지 0.20% = 0.50%

[수익 구조]
  BTC 현재 가격 ~1억 5천만원 기준:
  스프레드 0.60% = 90만원 → 수수료 75만원 = 순수익 15만원 / 1BTC
  스프레드 1.00% = 150만원 → 수수료 75만원 = 순수익 75만원 / 1BTC
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

# 스캔 대상 코인 (업비트+빗썸 공통 상장 종목)
SCAN_SYMBOLS = ["BTC", "ETH", "SOL", "XRP", "DOGE"]

# 수량 설정 (스캔용 — 실제 포지션은 자본 기준)
DEFAULT_QUANTITY = {
    "BTC":  0.001,   # ~15만원
    "ETH":  0.01,    # ~3만원
    "SOL":  0.1,     # ~1.5만원
    "XRP":  100.0,   # ~6만원
    "DOGE": 1000.0,  # ~4만원
}

SCAN_INTERVAL_SEC = 60   # 1분 주기


class KRWCrossScanner:
    """
    업비트↔빗썸 실시간 가격 차익 스캐너.

    Args:
        ev_engine: EVEngine 인스턴스
        upbit_client: pyupbit 클라이언트 (가격 조회용)
        signal_callback: 신호 발생 시 호출될 콜백 함수
        interval_sec: 스캔 주기 (초)
    """

    def __init__(
        self,
        ev_engine,
        signal_callback=None,
        interval_sec: int = SCAN_INTERVAL_SEC,
    ) -> None:
        self.engine = ev_engine
        self.signal_callback = signal_callback
        self.interval_sec = interval_sec
        self._signal_count = 0
        self._scan_count = 0

    @staticmethod
    def _get_upbit_price(symbol: str) -> float | None:
        """업비트 현재가 조회 (pyupbit)."""
        try:
            import pyupbit
            price = pyupbit.get_current_price(f"KRW-{symbol}")
            return float(price) if price else None
        except Exception as e:
            logger.error(f"[Scanner] 업비트 {symbol} 가격 조회 실패: {e}")
            return None

    @staticmethod
    def _get_bithumb_price(symbol: str) -> float | None:
        """빗썸 현재가 조회 (pybithumb)."""
        try:
            import pybithumb
            price = pybithumb.get_current_price(symbol)
            return float(price) if price else None
        except Exception as e:
            logger.error(f"[Scanner] 빗썸 {symbol} 가격 조회 실패: {e}")
            return None

    async def scan_once(self) -> list:
        """
        전체 코인에 대해 1회 스프레드 스캔.

        Returns:
            발생한 ArbitrageSignal 리스트
        """
        signals = []
        self._scan_count += 1

        for symbol in SCAN_SYMBOLS:
            try:
                # 업비트/빗썸 동시 조회 (asyncio.gather로 병렬화)
                p_upbit, p_bithumb = await asyncio.gather(
                    asyncio.to_thread(self._get_upbit_price, symbol),
                    asyncio.to_thread(self._get_bithumb_price, symbol),
                )

                if p_upbit is None or p_bithumb is None:
                    continue

                spread_pct = abs(p_upbit - p_bithumb) / min(p_upbit, p_bithumb) * 100

                quantity = DEFAULT_QUANTITY.get(symbol, 0.01)
                sig = self.engine.calc_krw_cross_arb(
                    p_upbit=p_upbit,
                    p_bithumb=p_bithumb,
                    symbol=symbol,
                    quantity=quantity,
                )

                if sig and sig.is_valid():
                    self._signal_count += 1
                    logger.info(
                        f"[KRW_Cross] ✅ 신호 #{self._signal_count} | "
                        f"{symbol} spread={spread_pct:.3f}% | "
                        f"{sig.details['direction']} | "
                        f"EV={sig.details['ev_krw']:,.0f}원"
                    )
                    signals.append(sig)

                    if self.signal_callback:
                        await self.signal_callback(sig)
                else:
                    logger.debug(
                        f"[KRW_Cross] {symbol}: "
                        f"업비트={p_upbit:,.0f} 빗썸={p_bithumb:,.0f} "
                        f"스프레드={spread_pct:.3f}% (임계 미달)"
                    )

            except Exception as e:
                logger.error(f"[KRW_Cross] {symbol} 스캔 오류: {e}")

        return signals

    async def run(self) -> None:
        """분 단위 실시간 스캔 루프 (main_daemon 태스크로 실행)."""
        logger.info(
            f"[KRW_Cross] 스캐너 시작 — 대상: {SCAN_SYMBOLS} | "
            f"주기: {self.interval_sec}초"
        )
        while True:
            t0 = time.monotonic()
            signals = await self.scan_once()

            elapsed = time.monotonic() - t0
            logger.info(
                f"[KRW_Cross] 스캔 #{self._scan_count} 완료 | "
                f"신호 {len(signals)}건 | 소요 {elapsed:.2f}초"
            )

            await asyncio.sleep(max(0, self.interval_sec - elapsed))
