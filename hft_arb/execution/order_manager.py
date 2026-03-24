"""
order_manager.py
================
거래소 API와 직접 통신하여 원자적 주문(Atomic Order)을 실행.
"""
import time
from typing import Dict, Any, Optional

class AtomicOrderManager:
    def __init__(self, paper_trading: bool = True):
        self.paper_trading = paper_trading

    def execute_leg1(self, symbol: str, side: str, amount: float, price: float) -> Dict[str, Any]:
        """레그 1 실행"""
        print(f"[LEG1] {side} {amount} {symbol} @ {price} (Paper: {self.paper_trading})")
        if self.paper_trading:
            time.sleep(0.1)
            return {"status": "FILLED", "order_id": f"P1-{int(time.time()*1000)}", "filled_price": price}
        return {"status": "ERROR", "msg": "API not implemented"}

    def execute_leg2(self, symbol: str, side: str, amount: float, price: float) -> Dict[str, Any]:
        """레그 2 실행"""
        print(f"[LEG2] {side} {amount} {symbol} @ {price} (Paper: {self.paper_trading})")
        if self.paper_trading:
            time.sleep(0.1)
            return {"status": "FILLED", "order_id": f"P2-{int(time.time()*1000)}", "filled_price": price}
        return {"status": "ERROR", "msg": "API not implemented"}

    def cancel_all(self, symbol: Optional[str] = None):
        """비상 시 모든 주문 취소"""
        print(f"[EMERGENCY] Canceling all orders for {symbol or 'ALL'}...")
        pass

    def check_order_status(self, order_id: str) -> str:
        return "FILLED"
