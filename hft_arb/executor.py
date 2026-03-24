"""
executor.py — 주문 실행 모듈 (paper_trading=True 고정)
=======================================================
[SecurityAuditor CRITICAL]
  - paper_trading=True 가 기본값이며, False로 변경하려면
    명시적 파라미터와 사용자 확인 절차가 필요하다.
  - 실거래 전환은 이 파일에서만 허용.
"""

import logging
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hft_arb.ev_engine import ArbitrageSignal

logger = logging.getLogger(__name__)


class ArbExecutor:
    """
    차익거래 주문 실행기.

    paper_trading=True (기본) 상태에서는 실제 주문 없이
    포지션 레지스트리에 기록만 한다.

    Args:
        paper_trading: True(기본)면 모의 거래, False면 실거래 (경고: 매우 위험)
        paper_positions: fail_safe.py와 공유하는 포지션 딕셔너리
    """

    def __init__(self, paper_trading: bool = True, paper_positions: dict | None = None):
        if not paper_trading:
            from hft_arb.clob_executor import RealClobExecutor
            self.real_executor = RealClobExecutor()
        
        self.paper_trading = paper_trading
        self.paper_positions = paper_positions if paper_positions is not None else {}

    async def execute(self, signal: "ArbitrageSignal") -> str | None:
        """
        차익거래 신호를 받아 주문 실행 (또는 paper 기록).
        """
        if not signal.is_valid():
            logger.warning(f"[Executor] 유효하지 않은 신호: {signal}")
            return None

        if self.paper_trading:
            return self._paper_execute(signal)
        else:
            return await self._real_execute(signal)

    async def _real_execute(self, signal: "ArbitrageSignal") -> str | None:
        """
        실거래 체결 로직.
        Polymarket 괴리 차익의 경우 양방향(Yes, No)을 동시에 시장가 매수한다.
        """
        if signal.strategy != "polymarket_arb":
            logger.warning(f"[Executor] {signal.strategy} 실거래는 아직 미지원입니다.")
            return None

        details = signal.details
        p_yes = details.get("p_yes")
        p_no = details.get("p_no")
        condition_id = signal.symbol
        
        # 실제 토큰 ID 가져오기 (매핑 필요)
        # 여기서는 signal.details에 token_ids가 있다고 가정
        token_ids = details.get("token_ids") 
        if not token_ids:
            logger.error("[Executor] Token IDs missing in signal details")
            return None

        # 1. Yes 매수
        yes_res = await self.real_executor.place_order(
            token_id=token_ids["yes"],
            amount_usd=signal.position_size / 2, # 분산 진입
            side="BUY"
        )
        
        # 2. No 매수
        no_res = await self.real_executor.place_order(
            token_id=token_ids["no"],
            amount_usd=signal.position_size / 2,
            side="BUY"
        )

        if yes_res and no_res:
            return f"real_{yes_res.get('orderID')}_{no_res.get('orderID')}"
        return None

    def _paper_execute(self, signal: "ArbitrageSignal") -> str:
        """
        Paper trading: 포지션 레지스트리에 기록.

        Args:
            signal: ArbitrageSignal

        Returns:
            포지션 ID
        """
        pos_id = f"paper_{signal.strategy}_{uuid.uuid4().hex[:8]}"
        self.paper_positions[pos_id] = {
            "id": pos_id,
            "strategy": signal.strategy,
            "symbol": signal.symbol,
            "ev_usd": signal.ev_usd,
            "ev_pct": signal.ev_pct,
            "position_size": signal.position_size,
            "details": signal.details,
            "status": "OPEN",
            "opened_at": signal.ts,
            "closed_at": None,
            "close_reason": None,
        }
        logger.info(
            f"[Paper] 포지션 기록 | ID={pos_id} | "
            f"전략={signal.strategy} | EV=${signal.ev_usd:.2f} ({signal.ev_pct:.4f}%)"
        )
        return pos_id

    def get_open_positions(self) -> list[dict]:
        """현재 오픈 paper 포지션 목록 반환."""
        return [p for p in self.paper_positions.values() if p.get("status") == "OPEN"]
