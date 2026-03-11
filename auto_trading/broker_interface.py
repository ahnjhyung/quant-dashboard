"""
Broker Interface
================
- Role: Real execution wrapper for multiple brokers.
- Safety: paper_trading=True by default, strict API key management.
- Implementation: Buying and selling orders, balance check.
"""

import logging
from typing import Optional
from config import PAPER_TRADING

class BrokerInterface:
    def __init__(self, paper_trading: bool = True):
        self.paper_trading = paper_trading or PAPER_TRADING
        self.logger = logging.getLogger("BrokerInterface")
        
        if not self.paper_trading:
            self.logger.warning("!!! REAL TRADING MODE IS ACTIVE !!!")
        else:
            self.logger.info("Paper trading mode active.")

    def place_order(self, ticker: str, side: str, amount: float, order_type: str = "MARKET") -> bool:
        """
        주문 실행 함수
        - side: 'BUY' or 'SELL'
        """
        if self.paper_trading:
            self.logger.info(f"[PAPER] {side} {amount} shares of {ticker} at MARKET price.")
            return True
        
        # TODO: 실제 브로커 API 연동 (Alpaca, 한국투자증권 등)
        self.logger.error(f"[REAL] Real trading order for {ticker} is not implemented yet.")
        return False

    def get_balance(self) -> float:
        """현재 잔고 조회"""
        if self.paper_trading:
            return 100000.0 # 모의 투자 기본 잔고
        return 0.0

    def get_positions(self) -> list:
        """현재 보유 포지션 조회"""
        return []

if __name__ == "__main__":
    broker = BrokerInterface(paper_trading=True)
    broker.place_order("TQQQ", "BUY", 10)
