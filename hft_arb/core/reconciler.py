"""
reconciler.py — 체결 후 검증 엔진

거래 완료 후 5초 이내에 실제 결과와 예상값을 비교하여
이상 징후를 감지하고 회로 차단기에 보고한다.
"""
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

MAX_PRICE_DEVIATION_PCT = 0.30   # 허용 최대 가격 편차 (%)  
MAX_QTY_DEVIATION_PCT   = 0.05   # 허용 최대 수량 편차 (5%)
MIN_PNL_WARN_PCT        = -0.10  # 이 아래로 손실나면 경고


@dataclass
class ReconciliationResult:
    passed: bool
    warnings: list[str]
    errors: list[str]
    actual_pnl_pct: float = 0.0


class Reconciler:
    """
    체결 후 5초 이내에 실행되어야 하는 4가지 검증.
    이상 감지 시 circuit_breaker.record_failure()를 호출한다.
    """

    def __init__(self, on_anomaly=None):
        """
        Args:
            on_anomaly: 이상 감지 시 호출할 콜백 (circuit_breaker.record_failure)
        """
        self.on_anomaly = on_anomaly

    async def verify_and_reconcile_executions(
        self,
        symbol: str,
        upbit_result: dict | None,
        bithumb_result: dict | None,
        upbit_side: str,
        bithumb_side: str,
        upbit_executor,
        bithumb_executor
    ) -> bool:
        """
        [팻테일 방어] 쌍방 주문 결과를 확인하고, 한 쪽만 성공했다면 비상 청산을 실행합니다.
        
        Args:
            symbol: 거래 대상 코인 기호 (예: 'DOGE')
            upbit_result: 업비트 주문 체결 결과 (성공 시 dict, 실패/None 시 실패로 간주)
            bithumb_result: 빗썸 주문 체결 결과 (성공 시 dict, 실패/None 시 실패로 간주)
            upbit_side: 업비트 주문 방향 ('buy' 또는 'sell')
            bithumb_side: 빗썸 주문 방향 ('buy' 또는 'sell')
            upbit_executor: 업비트 주문 실행기 인스턴스 (비상 청산용)
            bithumb_executor: 빗썸 주문 실행기 인스턴스 (비상 청산용)
            
        Returns:
            bool: 무사히 양쪽 체결(True) 또는 비상 청산 발생/양쪽 실패(False)
        """
        upbit_success = upbit_result is not None and upbit_result.get("status") == "executed"
        bithumb_success = bithumb_result is not None and bithumb_result.get("status") == "executed"

        if upbit_success and bithumb_success:
            logger.info(f"[{symbol}] 양쪽 거래소 체결 성공 확인. 정상 차익 달성.")
            return True

        if not upbit_success and not bithumb_success:
            logger.warning(f"[{symbol}] 양쪽 거래소 모두 주문 실패. 레깅 리스크 없음.")
            return False

        # 레깅 리스크 발생: 한 쪽만 체결됨
        logger.error(f"🚨 [CRITICAL] 레깅 리스크 감지! [{symbol}] "
                     f"Upbit 성공: {upbit_success}, Bithumb 성공: {bithumb_success}")

        # 체결된 쪽의 물량을 즉시 반대로 던져버림 (Unwind)
        if upbit_success:
            unwind_side = "sell" if upbit_side == "buy" else "buy"
            qty = upbit_result.get("executed_volume", 0)
            if qty > 0:
                logger.warning(f"[{symbol}] 업비트 {unwind_side} {qty:,.4f} 시장가 청산 시도 (Unwind)")
                try:
                    await upbit_executor.execute_order(symbol, unwind_side, volume=qty, is_market=True)
                    logger.info(f"[{symbol}] 업비트 비상 청산 완료. 단방향 위험 제거됨.")
                except Exception as e:
                    logger.critical(f"FATAL: 업비트 비상 청산조차 실패함! 100% 수동 개입 필요! {e}")
            else:
                logger.error("업비트 성공이나 체결 수량이 0임. 청산 생략.")
                
        elif bithumb_success:
            unwind_side = "sell" if bithumb_side == "buy" else "buy"
            qty = bithumb_result.get("executed_volume", 0)
            if qty > 0:
                logger.warning(f"[{symbol}] 빗썸 {unwind_side} {qty:,.4f} 시장가 청산 시도 (Unwind)")
                try:
                    await bithumb_executor.execute_order(symbol, unwind_side, volume=qty, is_market=True)
                    logger.info(f"[{symbol}] 빗썸 비상 청산 완료. 단방향 위험 제거됨.")
                except Exception as e:
                    logger.critical(f"FATAL: 빗썸 비상 청산조차 실패함! 100% 수동 개입 필요! {e}")
            else:
                logger.error("빗썸 성공이나 체결 수량이 0임. 청산 생략.")

        if self.on_anomaly:
            self.on_anomaly(f"Legging Risk 발생으로 비상 청산 트리거됨 ({symbol})")

        return False

    def reconcile(
        self,
        expected_buy_price: float,
        actual_buy_price: float,
        expected_sell_price: float,
        actual_sell_price: float,
        expected_qty: float,
        actual_buy_qty: float,
        actual_sell_qty: float,
        expected_pnl_pct: float,
        fee_rate: float = 0.0015,
    ) -> ReconciliationResult:
        """
        체결 결과 검증 실행.

        Returns:
            ReconciliationResult — 통과 여부 및 경고/오류 상세
        """
        errors: list[str] = []
        warnings: list[str] = []

        # R1: 매수 가격 편차 확인
        buy_dev = abs(actual_buy_price - expected_buy_price) / expected_buy_price * 100
        if buy_dev > MAX_PRICE_DEVIATION_PCT:
            errors.append(
                f"R1_BUY_PRICE: 편차 {buy_dev:.3f}% > {MAX_PRICE_DEVIATION_PCT}%"
            )

        # R2: 매도 가격 편차 확인
        sell_dev = abs(actual_sell_price - expected_sell_price) / expected_sell_price * 100
        if sell_dev > MAX_PRICE_DEVIATION_PCT:
            errors.append(
                f"R2_SELL_PRICE: 편차 {sell_dev:.3f}% > {MAX_PRICE_DEVIATION_PCT}%"
            )

        # R3: 수량 불일치 확인
        qty_dev_buy  = abs(actual_buy_qty  - expected_qty) / expected_qty * 100
        qty_dev_sell = abs(actual_sell_qty - expected_qty) / expected_qty * 100
        if qty_dev_buy > MAX_QTY_DEVIATION_PCT * 100:
            errors.append(f"R3_QTY_BUY: 편차 {qty_dev_buy:.2f}%")
        if qty_dev_sell > MAX_QTY_DEVIATION_PCT * 100:
            errors.append(f"R3_QTY_SELL: 편차 {qty_dev_sell:.2f}%")

        # R4: 실제 손익 계산 및 이상 감지
        actual_gross = (actual_sell_price - actual_buy_price) / actual_buy_price * 100
        actual_pnl = actual_gross - (fee_rate * 200)
        if actual_pnl < MIN_PNL_WARN_PCT:
            warnings.append(
                f"R4_PNL: 실제 손익 {actual_pnl:.4f}% < 경고선 {MIN_PNL_WARN_PCT}%"
            )
        if actual_pnl < expected_pnl_pct * 0.5:  # 예상 수익의 50% 미달
            warnings.append(
                f"R4_PNL_GAP: 실제({actual_pnl:.4f}%) < 예상({expected_pnl_pct:.4f}%) × 50%"
            )

        passed = len(errors) == 0

        if errors and self.on_anomaly:
            self.on_anomaly(f"Reconciliation Errors: {'; '.join(errors)}")

        if errors:
            logger.critical(f"[RECONCILER] 검증 실패: {errors}")
        elif warnings:
            logger.warning(f"[RECONCILER] 경고: {warnings}")
        else:
            logger.info(
                f"[RECONCILER] 검증 통과 | 실제 손익: {actual_pnl:+.4f}%"
            )

        return ReconciliationResult(
            passed=passed,
            warnings=warnings,
            errors=errors,
            actual_pnl_pct=actual_pnl,
        )


# ──────────────────────────── 단독 테스트 ────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(message)s")

    r = Reconciler()

    print("\n=== 정상 케이스 ===")
    result = r.reconcile(
        expected_buy_price=84000, actual_buy_price=84020,
        expected_sell_price=84900, actual_sell_price=84880,
        expected_qty=0.005, actual_buy_qty=0.005, actual_sell_qty=0.005,
        expected_pnl_pct=0.70,
    )
    assert result.passed, result.errors
    print(f">>> 통과 | PnL: {result.actual_pnl_pct:+.4f}% | PASS")

    print("\n=== 가격 편차 초과 케이스 ===")
    result = r.reconcile(
        expected_buy_price=84000, actual_buy_price=84400,  # 0.48% 편차
        expected_sell_price=84900, actual_sell_price=84900,
        expected_qty=0.005, actual_buy_qty=0.005, actual_sell_qty=0.005,
        expected_pnl_pct=0.70,
    )
    assert not result.passed
    print(f">>> 오류 감지: {result.errors[0]} | PASS")
    print("\n모든 테스트 통과 [PASS]")
