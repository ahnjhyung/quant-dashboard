"""
unwind_engine.py — 긴급 청산 엔진

레그 리스크 발생 시 (한쪽만 체결) 즉시 반대 주문으로
포지션을 청산하여 무방비 노출을 최소화한다.
"""
import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

MAX_UNWIND_ATTEMPTS = 3         # 청산 최대 재시도 횟수
UNWIND_RETRY_DELAY = 0.5        # 재시도 간격 (초)
MARKET_ORDER_SLIPPAGE = 0.002   # 시장가 주문 슬리피지 (긴급 청산이므로 더 큰 슬리피지 허용)


class UnwindEngine:
    """
    긴급 청산 엔진.
    한쪽 레그만 체결된 위험 상황에서 즉시 반대 주문을 실행한다.
    """

    def __init__(self, paper_trading: bool = True):
        self.paper_trading = paper_trading
        if paper_trading:
            logger.info("[UNWIND] paper_trading=True — 실 청산 차단됨")

    async def unwind(
        self,
        filled_exchange: str,
        filled_side: str,
        filled_qty: float,
        filled_price: float,
        symbol: str,
    ) -> dict:
        """
        체결된 레그를 반대 방향으로 즉시 청산한다.

        Args:
            filled_exchange: 체결된 거래소
            filled_side: 체결된 방향 ("buy" or "sell")
            filled_qty: 체결 수량
            filled_price: 체결 가격
            symbol: 거래 심볼

        Returns:
            dict — unwind 결과 (success, pnl, 재시도 횟수)
        """
        unwind_side = "sell" if filled_side == "buy" else "buy"
        logger.critical(
            f"[UNWIND] 긴급 청산 시작 — {filled_exchange} {unwind_side} "
            f"{filled_qty:.6f} {symbol}"
        )

        for attempt in range(1, MAX_UNWIND_ATTEMPTS + 1):
            try:
                result = await self._market_order(
                    exchange=filled_exchange,
                    side=unwind_side,
                    qty=filled_qty,
                    symbol=symbol,
                )
                if result["success"]:
                    pnl = self._estimate_unwind_loss(
                        entry_price=filled_price,
                        exit_price=result["price"],
                        qty=filled_qty,
                        side=filled_side,
                    )
                    logger.warning(
                        f"[UNWIND] 청산 완료 (시도 {attempt}/{MAX_UNWIND_ATTEMPTS}) "
                        f"| 예상 손실: {pnl:+.4f}%"
                    )
                    return {
                        "success": True,
                        "attempt": attempt,
                        "unwind_price": result["price"],
                        "pnl_pct": pnl,
                    }
            except Exception as e:
                logger.error(f"[UNWIND] 청산 시도 {attempt} 실패: {e}")

            if attempt < MAX_UNWIND_ATTEMPTS:
                await asyncio.sleep(UNWIND_RETRY_DELAY)

        # 모든 재시도 실패 — CRITICAL 알림 필요
        logger.critical(
            f"[UNWIND] {MAX_UNWIND_ATTEMPTS}회 청산 모두 실패! "
            "수동 개입 즉시 필요! (alerter 호출 필요)"
        )
        return {
            "success": False,
            "attempt": MAX_UNWIND_ATTEMPTS,
            "pnl_pct": None,
            "error": "ALL_UNWIND_ATTEMPTS_FAILED",
        }

    # ──────────────────────────── Private ────────────────────────────

    async def _market_order(self, exchange: str, side: str, qty: float, symbol: str) -> dict:
        """시장가 청산 주문 (paper 또는 실거래)"""
        if self.paper_trading:
            await asyncio.sleep(0.1)
            # 시장가 주문은 슬리피지가 더 큼
            slippage = MARKET_ORDER_SLIPPAGE if side == "buy" else -MARKET_ORDER_SLIPPAGE
            price = 84000.0 * (1 + slippage)  # 실제 환경에서는 실시간 호가 조회
            order_id = f"UNWIND-{exchange[:2].upper()}-{int(time.time() * 1000)}"
            logger.debug(f"[PAPER UNWIND] {exchange} {side} {qty:.6f} @ {price:.2f}")
            return {"success": True, "price": price, "order_id": order_id}
        else:
            raise NotImplementedError(
                "[SECURITY] 실거래 청산은 broker_interface.py를 통해서만 실행 가능합니다."
            )

    @staticmethod
    def _estimate_unwind_loss(
        entry_price: float, exit_price: float, qty: float, side: str
    ) -> float:
        """청산 손실 추정 (%)"""
        if side == "buy":
            return (exit_price - entry_price) / entry_price * 100
        else:
            return (entry_price - exit_price) / entry_price * 100


# ──────────────────────────── 단독 테스트 ────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(message)s")

    async def main():
        uw = UnwindEngine(paper_trading=True)

        print("\n=== 긴급 청산 테스트 (매수 포지션 → 즉시 매도 청산) ===")
        result = await uw.unwind(
            filled_exchange="binance",
            filled_side="buy",
            filled_qty=0.005,
            filled_price=84000.0,
            symbol="BTC-USDT",
        )
        assert result["success"], f"청산 실패: {result}"
        print(f">>> 청산 완료 | 손실: {result['pnl_pct']:+.4f}% | PASS")

    asyncio.run(main())
