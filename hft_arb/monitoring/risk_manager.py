"""
risk_manager.py
===============
100% 집중 배정 (Full Throttled) 매니저.
사용자가 할당한 소액 안에서 최대로 주문 사이즈를 결정함.
"""
from typing import Dict, Any

class RiskManager:
    def __init__(self, daily_loss_limit: float = -3.0):
        self.daily_loss_limit = daily_loss_limit
        self.daily_pnl = 0.0

    def calculate_order_size(self, balance: float, symbol: str) -> float:
        """
        사용자 요청: 100% 몰빵.
        수수료 및 슬리피지 여유 1%를 제외한 전액 리턴.
        """
        if self.daily_pnl < self.daily_loss_limit:
            print(f"[RISK] Daily Loss Limit Reached ({self.daily_pnl}%). NO TRADING.")
            return 0.0
            
        return balance * 0.99  # 99% 투입 (1% 예비비)

    def update_pnl(self, net_pnl_pct: float):
        self.daily_pnl += net_pnl_pct
        if self.daily_pnl < self.daily_loss_limit:
            print(f"[CIRCUIT BREAKER] {self.daily_pnl}% Loss. Shutting down for the day.")
