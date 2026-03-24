"""
fail_safe.py — 연결 끊김 Fail-safe 포지션 청산 모듈
=====================================================
[SecurityAuditor HIGH] 검수 대상:
  - WebSocket 재접속 실패 시 paper 포지션 전량 청산 기록
  - 최대 재접속 초과 시 데몬 종료 전 알림 발송
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class FailSafeManager:
    """
    WebSocket 연결 실패 시 포지션 청산을 수행하는 Fail-safe 관리자.

    paper_trading=True 환경에서 'CLOSED' 기록을 남기고,
    실거래 연동 시에는 거래소 API를 호출하여 실제 청산.

    Args:
        paper_positions: paper 포지션 레지스트리 (executor.py 공유)
        notifier_fn: 알림 전송 함수 (선택적)
    """

    def __init__(self, paper_positions: dict, notifier_fn=None):
        self.paper_positions = paper_positions
        self.notifier_fn = notifier_fn
        self._triggered = False

    async def trigger(self, reason: str = "WS Disconnect") -> None:
        """
        Fail-safe 발동: 모든 paper 포지션 청산 기록.

        Args:
            reason: fail-safe 발동 이유 (로그용)
        """
        if self._triggered:
            return  # 중복 발동 방지
        self._triggered = True

        ts = time.time()
        closed_count = 0

        for pos_id, pos in list(self.paper_positions.items()):
            if pos.get("status") == "OPEN":
                self.paper_positions[pos_id]["status"] = "CLOSED_FAILSAFE"
                self.paper_positions[pos_id]["closed_at"] = ts
                self.paper_positions[pos_id]["close_reason"] = reason
                closed_count += 1
                logger.warning(
                    f"[FailSafe] 포지션 청산: {pos_id} | "
                    f"전략={pos.get('strategy')} | 이유={reason}"
                )

        logger.critical(
            f"[FailSafe] 발동 완료 | 청산 포지션 수: {closed_count} | 이유: {reason}"
        )

        if self.notifier_fn:
            try:
                await self.notifier_fn(
                    f"🚨 [FailSafe] WS 연결 실패로 {closed_count}개 포지션 청산\n이유: {reason}"
                )
            except Exception as e:
                logger.error(f"[FailSafe] 알림 전송 실패: {e}")

    def reset(self) -> None:
        """재접속 성공 시 fail-safe 플래그 초기화."""
        self._triggered = False
        logger.info("[FailSafe] 리셋 완료 (재접속 성공)")
