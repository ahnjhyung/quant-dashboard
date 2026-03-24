"""
validator.py
============
거래 진입 전 5중 안전 검증 수행.
모든 항목 통과 시에만 SIGNAL_FOUND -> VALIDATING -> EXECUTING_LEG1 가능.
"""
from typing import Dict, Any, Tuple
import time

class TradeValidator:
    def __init__(self, min_spread: float = 0.5, max_api_latency: float = 0.5):
        self.min_spread = min_spread
        self.max_api_latency = max_api_latency

    def validate_pre_trade(self, signal_context: Dict[str, Any]) -> Tuple[bool, str]:
        """진입 전 검증 로직 (Table V1~V6)"""
        
        # 1. 스프레드 검증 (수수료 대비 넉넉한지)
        spread = signal_context.get("premium", 0.0)
        if spread < self.min_spread:
            return False, f"Inadequate Spread: {spread:.2f}% < {self.min_spread}%"

        # 2. 잔고 검증 (주문 가능 금액 확인)
        # TODO: 실제 API 연동 시 잔고 체크 로직 추가
        if not signal_context.get("has_balance", False):
            return False, "Insufficient Balance for 100% Allocation"

        # 3. 데이터 신선도 (Data Age)
        ts = signal_context.get("timestamp", 0)
        age = time.time() - ts
        if age > 2.0: # 2초 이상 된 데이터는 위험
            return False, f"Stale Data: {age:.2f}s old"

        # 4. API 지연 시간 (Latency)
        latency = signal_context.get("latency", 0)
        if latency > self.max_api_latency:
            return False, f"High Latency: {latency:.2f}s"

        # 5. 거래소 상태 (Exchange Status)
        if not signal_context.get("exchanges_stable", True):
            return False, "Exchange Maintenance or Instability"

        return True, "Valid"

    def validate_post_trade(self, execution_context: Dict[str, Any]) -> bool:
        """체결 후 사후 검증"""
        # 체결 가격이 예상 리미트를 크게 벗어났는지 확인
        expected = execution_context.get("expected_price")
        actual = execution_context.get("actual_price")
        
        if expected and actual:
            slippage = abs(actual - expected) / expected * 100
            if slippage > 0.5: # 0.5% 넘는 슬리피지 발생 시 경고
                print(f"⚠️ [WARNING] High Slippage detected: {slippage:.2f}%")
                return False
        
        return True
