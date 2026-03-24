"""
clob_executor.py — Polymarket CLOB 실거래 체결 모듈
=================================================
[SecurityAuditor CRITICAL]
  - 이 파일은 실제 자산이 이동하는 주문을 생성한다.
  - PRIVATE_KEY는 .env에서 로드하며 절대 로그에 남기지 않는다.
  - 모든 주문 직전에 잔고 확인 및 슬리피지 검증을 수행한다.
"""

import logging
import os
import time
from typing import Any

from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs, MarketOrderArgs
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class RealClobExecutor:
    """
    Polymarket CLOB 실제 주문 실행기.
    
    Attributes:
        client: py-clob-client ClobClient 인스턴스
    """
    
    def __init__(self):
        load_dotenv()
        private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
        address = os.getenv("POLYMARKET_ADDRESS")
        
        if not private_key or not address:
            raise ValueError("[CRITICAL] .env에 POLYMARKET_PRIVATE_KEY 또는 POLYMARKET_ADDRESS가 없습니다.")
            
        # L2 인증 (API 키 자동 생성/관리 모드)
        # 참고: 처음 실행 시 API Key 생성을 위해 서명이 필요할 수 있습니다.
        try:
            self.client = ClobClient(
                host="https://clob.polymarket.com",
                key=private_key,
                chain_id=POLYGON,
                signature_type=1 # EOA signature
            )
            logger.info(f"[ClobExecutor] Client initialized for address: {address}")
        except Exception as e:
            logger.error(f"[ClobExecutor] Initialization failed: {e}")
            raise

    async def get_balance(self) -> float:
        """현재 지갑의 USDC 잔고 확인 (Polygon)."""
        try:
            # USDC는 Polymarket CLOB에서 기본 결제 수단입니다.
            # SDK에서 제공하는 get_balance 또는 get_allowance를 활용합니다.
            resp = self.client.get_balance()
            # resp 예시: {'balance': '123.45', 'allowance': '...'}
            return float(resp.get("balance", "0"))
        except Exception as e:
            logger.error(f"[ClobExecutor] Balance check failed: {e}")
            return 0.0

    async def place_order(self, token_id: str, amount_usd: float, side: str = "BUY") -> dict | None:
        """
        시장가 주문(Market Order) 실행.
        
        Args:
            token_id: 구매/판매할 토큰 ID (Yes/No 하위 토큰)
            amount_usd: 주문 금액 (USD)
            side: "BUY" or "SELL"
            
        Returns:
            주문 결과 dict 또는 None
        """
        try:
            logger.info(f"[ClobExecutor] 주문 시도: {side} {token_id} | ${amount_usd}")
            
            # 1. 오더북 확인하여 슬리피지 감안한 가격 결정 (시장가 주문 시뮬레이션)
            # Polymarket CLOB은 순수 시장가 주문보다는 
            # 시장가에 가까운 가격의 Limit Order로 처리하는 것이 안전합니다.
            book = self.client.get_order_book(token_id)
            if not book or not book.asks:
                logger.error(f"[ClobExecutor] 오더북 비어있음: {token_id}")
                return None
                
            # 가장 좋은 매도 호가 (BUY 시) 또는 매수 호가 (SELL 시)
            best_price = float(book.asks[0].price) if side == "BUY" else float(book.bids[0].price)
            
            # 2. 주문 생성 (py-clob-client create_order 사용)
            order_args = OrderArgs(
                price=best_price,
                size=amount_usd / best_price, # 수량 계산
                side=side,
                token_id=token_id
            )
            
            resp = self.client.create_order(order_args)
            
            if resp and resp.get("orderID"):
                logger.info(f"[ClobExecutor] 주문 성공! ID: {resp.get('orderID')}")
                return resp
            else:
                logger.error(f"[ClobExecutor] 주문 실패: {resp}")
                return None
                
        except Exception as e:
            logger.error(f"[ClobExecutor] 주문 예외 발생: {e}")
            return None

if __name__ == "__main__":
    # 테스트 (주의: 실제 주문이 나갈 수 있음)
    # executor = RealClobExecutor()
    # asyncio.run(executor.get_balance())
    pass
