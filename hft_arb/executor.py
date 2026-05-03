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
            from hft_arb.upbit_executor import UpbitExecutor
            from hft_arb.bithumb_executor import BithumbExecutor
            import config
            
            logger.warning("=" * 60)
            logger.warning("  [EXECUTOR] !!! REAL TRADING MODE IS ACTIVE !!!")
            logger.warning("  [EXECUTOR] EVERY ORDER WILL BE PLACED ON EXCHANGES.")
            logger.warning("=" * 60)

            # Polymarket은 가스비(MATIC)가 없으면 초기화에 실패할 수 있으므로 예외처리
            try:
                self.real_executor = RealClobExecutor()
                logger.info("[Executor] Polymarket 실매매 엔진(RealClobExecutor) 로드 성공")
            except Exception as e:
                logger.error(f"[Executor] Polymarket 실매매 엔진 초기화 실패: {e}")
                self.real_executor = None

            self.upbit_exec = UpbitExecutor(paper_trading=False)
            self.bithumb_exec = BithumbExecutor(config.BITHUMB_ACCESS_KEY, config.BITHUMB_SECRET_KEY, paper_trading=False)
        
        self.paper_trading = paper_trading
        self.paper_positions = paper_positions if paper_positions is not None else {}

    async def execute(self, signal: "ArbitrageSignal") -> str | None:
        """
        차익거래 신호를 받아 주문 실행 (또는 paper 기록).
        """
        if getattr(signal, "is_valid", lambda: False)():
            pass # Method exists but might be handled differently depending on context
            
        if hasattr(signal, "is_valid") and not signal.is_valid():
            # [수정] 수천 번 발생하는 -EV 신호에 대해 Warning을 출력하면 렉이 발생하므로 Debug로 내립니다.
            # logger.debug(f"[Executor] EV가 0 이하인 신호 폐기: {signal.strategy} (EV: {signal.ev_pct:.2f}%)")
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
        if signal.strategy == "krw_cross_arb":
            direction = signal.details.get("direction")
            symbol = signal.symbol
            p_upbit = signal.details.get("p_upbit")
            p_bithumb = signal.details.get("p_bithumb")

            calc_krw = signal.details.get("order_krw", 0.0)
            MIN_ORDER_KRW = 5000.0

            import asyncio

            if direction == "빗썸매수→업비트매도":
                bithumb_krw = self.bithumb_exec.get_balance("KRW") or 0.0
                upbit_btc   = self.upbit_exec.get_balance(symbol) or 0.0

                # [SoftwareEngineer] 적응형 포지션 사이징:
                # 가진 돈(빗썸KRW)과 팔 수 있는 BTC(업비트BTC×가격) 중 작은 쪽으로 주문금액 축소
                upbit_btc_as_krw = upbit_btc * p_upbit
                trade_krw = min(calc_krw, bithumb_krw, upbit_btc_as_krw)

                if trade_krw < MIN_ORDER_KRW:
                    logger.warning(
                        f"[Executor] 실거래 포기 (최소금액 미달): "
                        f"가용={trade_krw:,.0f}원 < 최소={MIN_ORDER_KRW:,.0f}원 "
                        f"(빗썸KRW={bithumb_krw:,.0f}, 업비트BTC={upbit_btc:.8f})"
                    )
                    return None

                trade_qty_upbit = trade_krw / p_upbit
                logger.info(
                    f"[Executor] 빗썸매수→업비트매도 | "
                    f"주문금액={trade_krw:,.0f}원 (원계획={calc_krw:,.0f}원 → 잔고조정) "
                    f"| BTC수량={trade_qty_upbit:.8f}"
                )

                res_buy, res_sell = await asyncio.gather(
                    asyncio.to_thread(self.bithumb_exec.buy_market, symbol, trade_krw),
                    asyncio.to_thread(self.upbit_exec.sell_market, symbol, trade_qty_upbit)
                )
                logger.info(f"[Live] 빗썸 매수:{res_buy} / 업비트 매도:{res_sell}")
                return "real_bithumb_buy_upbit_sell"

            elif direction == "업비트매수→빗썸매도":
                upbit_krw   = self.upbit_exec.get_balance("KRW") or 0.0
                bithumb_btc = self.bithumb_exec.get_balance(symbol) or 0.0

                # [SoftwareEngineer] 적응형 포지션 사이징:
                # 가진 돈(업비트KRW)과 팔 수 있는 BTC(빗썸BTC×가격) 중 작은 쪽으로 주문금액 축소
                bithumb_btc_as_krw = bithumb_btc * p_bithumb
                trade_krw = min(calc_krw, upbit_krw, bithumb_btc_as_krw)

                if trade_krw < MIN_ORDER_KRW:
                    logger.warning(
                        f"[Executor] 실거래 포기 (최소금액 미달): "
                        f"가용={trade_krw:,.0f}원 < 최소={MIN_ORDER_KRW:,.0f}원 "
                        f"(업비트KRW={upbit_krw:,.0f}, 빗썸BTC={bithumb_btc:.8f})"
                    )
                    return None

                trade_qty_bithumb = trade_krw / p_bithumb
                logger.info(
                    f"[Executor] 업비트매수→빗썸매도 | "
                    f"주문금액={trade_krw:,.0f}원 (원계획={calc_krw:,.0f}원 → 잔고조정) "
                    f"| BTC수량={trade_qty_bithumb:.8f}"
                )

                res_buy, res_sell = await asyncio.gather(
                    asyncio.to_thread(self.upbit_exec.buy_market, symbol, trade_krw),
                    asyncio.to_thread(self.bithumb_exec.sell_market, symbol, trade_qty_bithumb)
                )
                logger.info(f"[Live] 업비트 매수:{res_buy} / 빗썸 매도:{res_sell}")
                return "real_upbit_buy_bithumb_sell"

        elif signal.strategy != "polymarket_arb":
            logger.warning(f"[Executor] {signal.strategy} 실거래는 아직 미지원입니다.")
            return None

        # Polymarket 실매매 엔진이 로드되지 않았으면 중단
        if self.real_executor is None:
            logger.error("[Executor] Polymarket 엔진이 비활성 상태입니다. (MATIC 가스비 확인 필요)")
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

        # Dual Order 동시 1세트 진입 (레그 리스크 방어)
        logger.info(f"[Executor] Polymarket Dual Order 시도: $ {signal.position_size:.2f} 투입")
        
        res = await self.real_executor.place_dual_order(
            yes_token=token_ids["yes"],
            no_token=token_ids["no"],
            amount_usd=signal.position_size,
            yes_price=p_yes,
            no_price=p_no
        )

        success_yes = res.get("yes_order")
        success_no = res.get("no_order")

        if success_yes and success_no:
            return f"real_{success_yes.get('orderID')}_{success_no.get('orderID')}"
        # 레그 리스크 발생 시 기록
        elif success_yes:
            return f"real_leg_yes_{success_yes.get('orderID')}"
        elif success_no:
            return f"real_leg_no_{success_no.get('orderID')}"
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
