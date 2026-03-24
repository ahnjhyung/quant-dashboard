"""
circuit_breaker.py — 회로 차단기

연속 실패, 일일 손실 한도, API 오류율을 감시하여
손실 확대를 자동으로 차단한다.
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerConfig:
    """회로 차단기 설정값 — paper_trading 모드에서는 더 엄격하게"""
    max_consecutive_failures: int = 3     # 연속 실패 허용 횟수
    cooldown_seconds: int = 600           # 차단 후 재가동 대기 (10분)
    max_daily_loss_pct: float = 3.0       # 일일 최대 손실률 (%)
    max_api_error_rate: float = 0.20      # API 오류율 임계치 (20%)
    extreme_kp_threshold: float = 10.0   # 극단적 프리미엄 임계치
    paper_trading: bool = True            # 기본값: 반드시 paper trading


class CircuitBreaker:
    """
    5가지 트리거를 감시하는 회로 차단기.
    HALT 발동 시 StateMachine.force_halt()를 호출한다.
    """

    def __init__(
        self,
        config: CircuitBreakerConfig,
        on_halt: Optional[Callable[[str], None]] = None,
    ):
        self.cfg = config
        self.on_halt = on_halt  # StateMachine.force_halt 콜백

        self._consecutive_failures = 0
        self._daily_loss_pct: float = 0.0
        self._daily_reset_date: date = date.today()
        self._api_call_count: int = 0
        self._api_error_count: int = 0
        self._halted: bool = False
        self._halt_reason: str = ""
        self._halt_time: Optional[float] = None

        if self.cfg.paper_trading:
            logger.info("[CIRCUIT BREAKER] paper_trading=True. 실거래 차단됨.")

    # ──────────────── 외부에서 호출하는 이벤트 핸들러 ────────────────

    def record_success(self):
        """거래 성공 시 연속 실패 카운터 초기화"""
        self._consecutive_failures = 0

    def record_failure(self, reason: str = ""):
        """거래 실패 또는 오류 시 호출"""
        self._consecutive_failures += 1
        logger.warning(f"[CB] Failure #{self._consecutive_failures}: {reason}")

        if self._consecutive_failures >= self.cfg.max_consecutive_failures:
            self._trigger_halt(
                f"연속 {self._consecutive_failures}회 실패: {reason}"
            )

    def record_api_call(self, success: bool):
        """API 호출마다 호출 — 오류율 모니터링"""
        self._api_call_count += 1
        if not success:
            self._api_error_count += 1

        if self._api_call_count >= 20:  # 20회 이상 집계 시에만 판단
            error_rate = self._api_error_count / self._api_call_count
            if error_rate > self.cfg.max_api_error_rate:
                self._trigger_halt(
                    f"API 오류율 {error_rate:.0%} > 임계치 {self.cfg.max_api_error_rate:.0%}"
                )

    def record_pnl(self, pnl_pct: float):
        """손익 기록 — 일일 손실 한도 체크"""
        self._reset_daily_if_needed()
        self._daily_loss_pct += pnl_pct

        if self._daily_loss_pct < -self.cfg.max_daily_loss_pct:
            self._trigger_halt(
                f"일일 손실 {self._daily_loss_pct:.2f}% "
                f"> 한도 -{self.cfg.max_daily_loss_pct:.1f}%"
            )

    def check_kp_risk(self, kp_pct: float) -> bool:
        """
        김치 프리미엄 극단값 체크.
        
        Returns:
            True if safe, False if extreme (신규 진입 차단)
        """
        if kp_pct > self.cfg.extreme_kp_threshold:
            logger.warning(
                f"[CB] 극단적 KP {kp_pct:.1f}% 감지 — 신규 진입 차단"
            )
            return False
        return True

    def is_halted(self) -> bool:
        """현재 차단 상태인지 반환 (쿨다운 만료 시 자동 해제)"""
        if not self._halted:
            return False
        # 쿨다운 만료 체크
        if self._halt_time and (time.time() - self._halt_time > self.cfg.cooldown_seconds):
            logger.info("[CB] 쿨다운 만료. 자동 재가동 허용.")
            self._halted = False
            self._consecutive_failures = 0
            return False
        remaining = int(self.cfg.cooldown_seconds - (time.time() - self._halt_time))
        logger.debug(f"[CB] 차단 중... 재가동까지 {remaining}초 남음")
        return True

    def get_status(self) -> dict:
        return {
            "halted": self._halted,
            "halt_reason": self._halt_reason,
            "consecutive_failures": self._consecutive_failures,
            "daily_loss_pct": round(self._daily_loss_pct, 4),
            "api_error_rate": (
                round(self._api_error_count / self._api_call_count, 4)
                if self._api_call_count > 0 else 0.0
            ),
            "paper_trading": self.cfg.paper_trading,
        }

    # ──────────────────────────── Private ────────────────────────────

    def _trigger_halt(self, reason: str):
        if self._halted:
            return  # 이미 차단 중
        self._halted = True
        self._halt_reason = reason
        self._halt_time = time.time()
        logger.critical(f"[CIRCUIT BREAKER] HALT 발동: {reason}")
        if self.on_halt:
            try:
                self.on_halt(reason)
            except Exception as e:
                logger.error(f"on_halt callback failed: {e}")

    def _reset_daily_if_needed(self):
        today = date.today()
        if today != self._daily_reset_date:
            self._daily_loss_pct = 0.0
            self._api_call_count = 0
            self._api_error_count = 0
            self._daily_reset_date = today
            logger.info("[CB] 일일 손익 카운터 초기화")


# ──────────────────────────── 단독 테스트 ────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(message)s")

    halted_reason = []
    cfg = CircuitBreakerConfig(max_consecutive_failures=3, cooldown_seconds=5)
    cb = CircuitBreaker(cfg, on_halt=lambda r: halted_reason.append(r))

    print("\n=== 연속 실패 차단 테스트 ===")
    cb.record_failure("API 타임아웃")
    cb.record_failure("잔고 부족")
    cb.record_failure("체결 실패")
    assert cb.is_halted(), "3회 실패 후 HALT 미발동"
    assert len(halted_reason) == 1
    print(">>> 연속 실패 차단: PASS")

    print("\n=== 쿨다운 만료 자동 해제 테스트 ===")
    time.sleep(6)
    assert not cb.is_halted(), "쿨다운 만료 후 자동 해제 실패"
    print(">>> 쿨다운 자동 해제: PASS")

    print("\n=== 일일 손실 한도 테스트 ===")
    cb.record_pnl(-1.5)
    cb.record_pnl(-1.8)
    assert cb.is_halted(), "일일 손실 한도 초과 HALT 미발동"
    print(">>> 일일 손실 한도 차단: PASS")
    print("\n모든 테스트 통과 ✅")
