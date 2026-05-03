"""
upbit_executor.py — 업비트 주문 실행기 (순수 Python REST API + JWT)
================================================================
[SecurityAuditor CRITICAL]
  - API 키(ACCESS, SECRET)는 config.py/.env 통해서만 로드
  - pyupbit 의존성을 제거하여 C컴파일 오류를 원천 차단
  - 실거래 전환은 명시적 사용자 승인 필요
"""

from __future__ import annotations

import hashlib
import logging
import os
import urllib.parse
import uuid
from typing import Any

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 수수료
FEE_UPBIT_TAKER = 0.0005   # 0.05%
BASE_URL = "https://api.upbit.com/v1"

try:
    import jwt as pyjwt
    PYJWT_AVAILABLE = True
except ImportError:
    PYJWT_AVAILABLE = False
    logger.warning("[Upbit] PyJWT 미설치 — pip install PyJWT")


def _make_jwt_token(access_key: str, secret_key: str, query_string: str | None = None) -> str:
    """Upbit JWT 생성."""
    payload: dict[str, Any] = {
        'access_key': access_key,
        'nonce': str(uuid.uuid4()),
    }
    if query_string:
        h = hashlib.new('sha512')
        h.update(query_string.encode('utf-8'))
        payload['query_hash'] = h.hexdigest()
        payload['query_hash_alg'] = 'SHA512'

    token = pyjwt.encode(payload, secret_key, algorithm='HS256')
    return f'Bearer {token}'


class UpbitExecutor:
    def __init__(self, paper_trading: bool = True):
        load_dotenv()
        access_key = os.getenv("UPBIT_ACCESS_KEY", "")
        secret_key = os.getenv("UPBIT_SECRET_KEY", "")

        if not access_key or not secret_key:
            logger.warning("[Upbit] API 키 미설정 — 페이퍼 모드 강제")
            paper_trading = True

        if not PYJWT_AVAILABLE and not paper_trading:
            logger.error("[Upbit] PyJWT 미설치 — 실거래 불가, 페이퍼 모드 강제")
            paper_trading = True

        self.paper_trading = paper_trading
        self._access_key = access_key
        self._secret_key = secret_key

        mode = "PAPER" if paper_trading else "LIVE"
        logger.info(f"[Upbit] 실행기 초기화 완료 [{mode}]")

    def _get(self, path: str, params: dict | None = None) -> Any:
        qs = urllib.parse.urlencode(params) if params else None
        url = f"{BASE_URL}{path}" + (f"?{qs}" if qs else "")
        headers = {
            'Authorization': _make_jwt_token(self._access_key, self._secret_key, qs),
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict | None = None) -> Any:
        qs = urllib.parse.urlencode(body) if body else None
        headers = {
            'Authorization': _make_jwt_token(self._access_key, self._secret_key, qs),
            'Content-Type': 'application/json',
        }
        resp = requests.post(f"{BASE_URL}{path}", json=body or {}, headers=headers, timeout=10)
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error(f"[Upbit] POST Error: {resp.text}")
            raise e
        return resp.json()

    def get_balance(self, currency: str = "KRW") -> float:
        if self.paper_trading:
            return 0.0
        try:
            accounts = self._get('/accounts')
            target = currency.upper()
            for acc in accounts:
                if acc.get('currency') == target:
                    return float(acc.get('balance', 0))
            return 0.0
        except Exception as e:
            logger.error(f"[Upbit] 잔고 조회 실패: {e}")
            return 0.0

    def buy_market(self, symbol: str, krw_amount: float) -> dict | None:
        """시장가 매수"""
        if krw_amount < 5000:
            logger.warning(f"[Upbit] 최소 주문 금액 미달: {krw_amount}원")
            return None

        if self.paper_trading:
            logger.info(f"[PAPER:Upbit BUY] {symbol}: {krw_amount:,.0f}원 시장가 매수 접수 (모의)")
            return {"paper": True, "side": "buy", "krw_amount": krw_amount}

        try:
            body = {
                "market": f"KRW-{symbol}",
                "side": "bid",
                "price": str(krw_amount),
                "ord_type": "price",
            }
            res = self._post("/orders", body)
            logger.info(f"[LIVE:Upbit BUY] {symbol} {krw_amount:,.0f}원 매수 체결: {res.get('uuid')}")
            return res
        except Exception as e:
            logger.error(f"[Upbit] 매수 실패: {e}")
            return None

    def sell_market(self, symbol: str, quantity: float) -> dict | None:
        """시장가 매도"""
        if self.paper_trading:
            logger.info(f"[PAPER:Upbit SELL] {symbol}: {quantity:.6f}개 시장가 매도 접수 (모의)")
            return {"paper": True, "side": "sell", "quantity": quantity}

        try:
            body = {
                "market": f"KRW-{symbol}",
                "side": "ask",
                "volume": str(quantity),
                "ord_type": "market",
            }
            res = self._post("/orders", body)
            logger.info(f"[LIVE:Upbit SELL] {symbol} {quantity:.6f}개 매도 체결: {res.get('uuid')}")
            return res
        except Exception as e:
            logger.error(f"[Upbit] 매도 실패: {e}")
            return None
