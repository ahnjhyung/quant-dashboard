"""
upbit_executor.py
=================
업비트 실거래 주문 실행 모듈 (김치 프리미엄 차익거래 전용)

[SecurityAuditor CRITICAL]
  - API Key는 반드시 config.py 경유 (os.environ 직접 사용 금지)
  - paper_trading=True 가 기본값
  - 잔고 확인 후 주문 실행 (V1 검증 내장)
"""
import logging
from typing import Optional

import pyupbit

from config import UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY

logger = logging.getLogger(__name__)


class UpbitExecutor:
    """
    업비트 실거래 주문 실행기 (김치 프리미엄 차익거래).

    Args:
        paper_trading: True(기본)면 모의 거래, False면 실거래
    """

    def __init__(self, paper_trading: bool = True):
        self.paper_trading = paper_trading

        if not paper_trading:
            if not UPBIT_ACCESS_KEY or not UPBIT_SECRET_KEY:
                raise ValueError(
                    "[CRITICAL] UPBIT_ACCESS_KEY 또는 UPBIT_SECRET_KEY가 .env에 없습니다."
                )
            self._upbit = pyupbit.Upbit(UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY)
            logger.info("[UpbitExecutor] 실거래 모드 초기화 완료.")
        else:
            self._upbit = None
            logger.info("[UpbitExecutor] 페이퍼 트레이딩 모드.")

    def get_krw_balance(self) -> float:
        """KRW 잔고 조회."""
        if self.paper_trading:
            return 1_000_000.0
        try:
            balances = self._upbit.get_balances()
            for b in balances:
                if b["currency"] == "KRW":
                    return float(b["balance"])
            return 0.0
        except Exception as e:
            logger.error(f"[UpbitExecutor] 잔고 조회 실패: {e}")
            return 0.0

    def get_crypto_balance(self, symbol: str) -> float:
        """코인 잔고 조회 (symbol: 'BTC', 'ETH', 'SOL')."""
        if self.paper_trading:
            return 0.0
        try:
            balances = self._upbit.get_balances()
            for b in balances:
                if b["currency"] == symbol:
                    return float(b["balance"])
            return 0.0
        except Exception as e:
            logger.error(f"[UpbitExecutor] {symbol} 잔고 조회 실패: {e}")
            return 0.0

    def buy_market_order(self, market: str, krw_amount: float) -> Optional[dict]:
        """
        시장가 매수 주문 (KRW 금액 기준).

        Args:
            market: 'KRW-BTC', 'KRW-ETH', 'KRW-SOL' 등
            krw_amount: 투자할 KRW 금액

        Returns:
            주문 결과 dict 또는 None
        """
        if krw_amount < 5000:
            logger.warning(f"[UpbitExecutor] 최소 주문 금액 미만: {krw_amount}")
            return None

        if self.paper_trading:
            logger.info(f"[UpbitExecutor][PAPER] BUY {market} {krw_amount:,.0f}KRW")
            return {"status": "PAPER_FILLED", "market": market, "volume": krw_amount, "side": "bid"}

        try:
            balance = self.get_krw_balance()
            if balance < krw_amount * 1.01:
                logger.error(f"[UpbitExecutor] 잔고 부족. 보유: {balance:,.0f} / 필요: {krw_amount:,.0f}")
                return None
            logger.info(f"[UpbitExecutor][LIVE] BUY {market} {krw_amount:,.0f}KRW")
            result = self._upbit.buy_market_order(market, krw_amount)
            logger.info(f"[UpbitExecutor][LIVE] 매수 완료: {result}")
            return result
        except Exception as e:
            logger.error(f"[UpbitExecutor] 매수 주문 예외: {e}")
            return None

    def sell_market_order(self, market: str, volume: float) -> Optional[dict]:
        """
        시장가 매도 주문 (코인 수량 기준).

        Args:
            market: 'KRW-BTC', 'KRW-ETH', 'KRW-SOL' 등
            volume: 매도할 코인 수량

        Returns:
            주문 결과 dict 또는 None
        """
        if volume <= 0:
            logger.warning(f"[UpbitExecutor] 매도 수량이 0 이하: {volume}")
            return None

        if self.paper_trading:
            logger.info(f"[UpbitExecutor][PAPER] SELL {market} {volume}")
            return {"status": "PAPER_FILLED", "market": market, "volume": volume, "side": "ask"}

        try:
            crypto_symbol = market.split("-")[1]
            balance = self.get_crypto_balance(crypto_symbol)
            if balance < volume:
                logger.error(f"[UpbitExecutor] {crypto_symbol} 잔고 부족. 보유: {balance} / 필요: {volume}")
                return None
            logger.info(f"[UpbitExecutor][LIVE] SELL {market} {volume}")
            result = self._upbit.sell_market_order(market, volume)
            logger.info(f"[UpbitExecutor][LIVE] 매도 완료: {result}")
            return result
        except Exception as e:
            logger.error(f"[UpbitExecutor] 매도 주문 예외: {e}")
            return None
