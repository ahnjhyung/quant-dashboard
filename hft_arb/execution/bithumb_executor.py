"""
bithumb_executor.py
===================
빗썸 실거래 주문 실행 모듈 (API v2.0 JWT 인증 적용)

[SecurityAuditor CRITICAL]
  - API Key는 config.py 경유
  - paper_trading=True 기본값
"""
import logging
import time
import uuid
import jwt
import requests
import hashlib
import urllib.parse
from typing import Optional

try:
    from config import BITHUMB_ACCESS_KEY, BITHUMB_SECRET_KEY
except ImportError:
    BITHUMB_ACCESS_KEY = ""
    BITHUMB_SECRET_KEY = ""

logger = logging.getLogger(__name__)

class BithumbExecutor:
    """
    빗썸 API v2.0 (Upbit 호환 규격) 실거래 주문 실행기.

    Args:
        paper_trading: True(기본)면 모의 거래, False면 실거래
    """
    
    BASE_URL = "https://api.bithumb.com/v1"

    def __init__(self, paper_trading: bool = True):
        self.paper_trading = paper_trading

        if not paper_trading:
            if not BITHUMB_ACCESS_KEY or not BITHUMB_SECRET_KEY:
                raise ValueError(
                    "[CRITICAL] BITHUMB_ACCESS_KEY 또는 BITHUMB_SECRET_KEY가 .env에 없습니다."
                )
            logger.info("[BithumbExecutor] 빗썸 API v2.0 실거래 모드 초기화 완료.")
        else:
            logger.info("[BithumbExecutor] 페이퍼 트레이딩 모드.")

    def _get_headers(self, query_params: dict = None) -> dict:
        """JWT 토큰 기반 인증 헤더 생성"""
        payload = {
            'access_key': BITHUMB_ACCESS_KEY,
            'nonce': str(uuid.uuid4()),
            'timestamp': round(time.time() * 1000)
        }
        
        if query_params:
            query_string = urllib.parse.urlencode(query_params).encode("utf-8")
            m = hashlib.sha512()
            m.update(query_string)
            query_hash = m.hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'

        jwt_token = jwt.encode(payload, BITHUMB_SECRET_KEY, algorithm='HS256')
        return {
            'Authorization': f'Bearer {jwt_token}',
            'Content-Type': 'application/json'
        }

    def _request(self, method: str, path: str, params: dict = None) -> Optional[dict]:
        url = self.BASE_URL + path
        headers = self._get_headers(params)
        
        try:
            if method == 'GET':
                res = requests.get(url, params=params, headers=headers)
            else:
                res = requests.post(url, json=params, headers=headers)
                
            res.raise_for_status()
            return res.json()
        except Exception as e:
            logger.error(f"[BithumbExecutor] API 요청 에러 ({method} {path}): {e}")
            if 'res' in locals() and res is not None:
                logger.error(f"[BithumbExecutor] 응답 내용: {res.text}")
            return None

    def get_krw_balance(self) -> float:
        """KRW 잔고 조회."""
        if self.paper_trading:
            return 1_000_000.0
            
        data = self._request('GET', '/accounts')
        if data is None:
            return 0.0
            
        for acct in data:
            if acct.get('currency') == 'KRW':
                return float(acct.get('balance', 0))
        return 0.0

    def get_crypto_balance(self, symbol: str) -> float:
        """코인 잔고 조회. symbol은 'BTC', 'DOGE' 등"""
        if self.paper_trading:
            return 0.0
            
        data = self._request('GET', '/accounts')
        if data is None:
            return 0.0
            
        for acct in data:
            if acct.get('currency') == symbol:
                return float(acct.get('balance', 0))
        return 0.0

    async def execute_order(self, market: str, side: str, volume: float = 0.0, is_market: bool = True) -> Optional[dict]:
        """
        비상 청산 등에서 호출하기 위함. market 포맷: 'KRW-BTC'
        """
        if side == "buy":
            return self.buy_market_order(market, volume)
        else:
            return self.sell_market_order(market, volume)

    def buy_market_order(self, market: str, krw_amount: float) -> Optional[dict]:
        """
        시장가 매수 (KRW 기준).
        빗썸 V2 API 최소주문: 5000원
        """
        if krw_amount < 5000:
            logger.warning(f"[BithumbExecutor] 최소 주문 금액 미만 (5000 KRW): {krw_amount}")
            return None

        if self.paper_trading:
            logger.info(f"[BithumbExecutor][PAPER] BUY {market} {krw_amount:,.0f}KRW")
            return {"status": "PAPER_FILLED", "volume": krw_amount, "side": "buy"}

        logger.info(f"[BithumbExecutor][LIVE] BUY {market} {krw_amount:,.0f}KRW")
        params = {
            'market': market,
            'side': 'bid',
            'price': str(krw_amount),
            'ord_type': 'price'
        }
        result = self._request('POST', '/orders', params)
        if result:
            logger.info(f"[BithumbExecutor][LIVE] 매수 결과: {result}")
            return result
        return None

    def sell_market_order(self, market: str, volume: float) -> Optional[dict]:
        """
        시장가 매도 (수량 기준).
        """
        if volume <= 0:
            return None

        if self.paper_trading:
            logger.info(f"[BithumbExecutor][PAPER] SELL {market} {volume}")
            return {"status": "PAPER_FILLED", "volume": volume, "side": "sell"}

        logger.info(f"[BithumbExecutor][LIVE] SELL {market} {volume}개")
        params = {
            'market': market,
            'side': 'ask',
            'volume': str(volume),
            'ord_type': 'market'
        }
        result = self._request('POST', '/orders', params)
        if result:
            logger.info(f"[BithumbExecutor][LIVE] 매도 결과: {result}")
            return result
        return None
