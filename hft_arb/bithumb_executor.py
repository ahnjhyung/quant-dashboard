"""
bithumb_executor.py — 빗썸 주문 실행기 (신 API v1, JWT HS256)
==============================================================
[보안 원칙]
  - API 키는 config.py/.env 통해서만 로드
  - paper_trading=True 기본값
  - 실거래 전환은 명시적 사용자 승인 필요

[빗썸 신 API 인증]
  - 빗썸 2024년 신규 API: /v1/* 엔드포인트
  - 인증: JWT HS256 (access_key + nonce:UUID + timestamp)
  - Authorization: Bearer {jwt_token}
  - 공식 문서: https://apidocs.bithumb.com/docs/인증-헤더-만들기

[전략]
  업비트↔빗썸 KRW 크로스 차익:
  - 코인 전송 불필요 (양쪽에 코인/KRW 예치)
  - 한쪽 매수 + 반대쪽 동시 매도
  - 네트워크 전송비 $0
"""

from __future__ import annotations

import hashlib
import logging
import time
import urllib.parse
import uuid
from typing import Any

import requests

logger = logging.getLogger(__name__)

# 수수료 (보수적)
FEE_BITHUMB_TAKER = 0.0025   # 0.25% (빗썸 기본 수수료)
BASE_URL = "https://api.bithumb.com"

# pybithumb은 공개 API (가격 조회) 전용으로만 유지
try:
    import pybithumb
    PYBITHUMB_AVAILABLE = True
except ImportError:
    PYBITHUMB_AVAILABLE = False
    logger.warning("[Bithumb] pybithumb 미설치 — pip install pybithumb")

try:
    import jwt as pyjwt
    PYJWT_AVAILABLE = True
except ImportError:
    PYJWT_AVAILABLE = False
    logger.warning("[Bithumb] PyJWT 미설치 — pip install PyJWT")


def _make_jwt_token(access_key: str, secret_key: str, query_string: str | None = None) -> str:
    """
    빗썸 신 API JWT HS256 인증 토큰 생성.

    Args:
        access_key: 빗썸 API Access Key
        secret_key: 빗썸 API Secret Key
        query_string: URL 인코딩된 쿼리 파라미터 (없으면 None)

    Returns:
        'Bearer {jwt_token}' 형식의 인증 헤더 값
    """
    payload: dict[str, Any] = {
        'access_key': access_key,
        'nonce': str(uuid.uuid4()),
        'timestamp': round(time.time() * 1000),
    }
    if query_string:
        h = hashlib.new('sha512')
        h.update(query_string.encode('utf-8'))
        payload['query_hash'] = h.hexdigest()
        payload['query_hash_alg'] = 'SHA512'

    token = pyjwt.encode(payload, secret_key, algorithm='HS256')
    return f'Bearer {token}'


class BithumbExecutor:
    """
    빗썸 주문 실행기 (신 API v1 + JWT HS256).

    Args:
        access_key: 빗썸 API Access Key
        secret_key: 빗썸 API Secret Key
        paper_trading: True=모의, False=실거래 (기본 True)
    """

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        paper_trading: bool = True,
    ) -> None:
        # [SecurityAuditor CRITICAL] 키 직접 노출 방지
        if not access_key or access_key.startswith("여기에"):
            logger.warning("[Bithumb] API 키 미설정 — 페이퍼 모드 강제")
            paper_trading = True

        if not PYJWT_AVAILABLE and not paper_trading:
            logger.error("[Bithumb] PyJWT 미설치 — 실거래 불가, 페이퍼 모드 강제")
            paper_trading = True

        self.paper_trading = paper_trading
        self._access_key = access_key
        self._secret_key = secret_key

        mode = "PAPER" if paper_trading else "LIVE"
        logger.info(f"[Bithumb] 실행기 초기화 완료 [{mode}]")

    # ── 내부 HTTP 헬퍼 ────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> Any:
        """빗썸 신 API GET 요청 (JWT 인증)."""
        qs = urllib.parse.urlencode(params) if params else None
        url = f"{BASE_URL}{path}" + (f"?{qs}" if qs else "")
        headers = {
            'Authorization': _make_jwt_token(self._access_key, self._secret_key, qs),
            'Content-Type': 'application/json',
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict | None = None) -> Any:
        """빗썸 신 API POST 요청 (JWT 인증)."""
        qs = urllib.parse.urlencode(body) if body else None
        headers = {
            'Authorization': _make_jwt_token(self._access_key, self._secret_key, qs),
            'Content-Type': 'application/json',
        }
        resp = requests.post(
            f"{BASE_URL}{path}",
            json=body or {},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str, params: dict | None = None) -> Any:
        """빗썸 신 API DELETE 요청 (JWT 인증)."""
        qs = urllib.parse.urlencode(params) if params else None
        url = f"{BASE_URL}{path}" + (f"?{qs}" if qs else "")
        headers = {
            'Authorization': _make_jwt_token(self._access_key, self._secret_key, qs),
            'Content-Type': 'application/json',
        }
        resp = requests.delete(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ── 공개 API (인증 불필요) ────────────────────────────────────

    def get_current_price(self, symbol: str = "BTC") -> float | None:
        """
        빗썸 현재가 조회 (공개 API).

        Args:
            symbol: 코인 심볼 (예: "BTC", "ETH", "DOGE")

        Returns:
            현재가(원) 또는 None
        """
        if not PYBITHUMB_AVAILABLE:
            return None
        try:
            price = pybithumb.get_current_price(symbol)
            return float(price)
        except Exception as e:
            logger.error(f"[Bithumb] {symbol} 현재가 조회 실패: {e}")
            return None

    # ── 비공개 API ───────────────────────────────────────────────

    def get_balance(self, currency: str = "KRW") -> float | None:
        """
        빗썸 잔고 조회 (신 API /v1/accounts).

        Args:
            currency: 통화 (예: "KRW", "BTC", "DOGE")

        Returns:
            사용 가능 잔고 또는 None
        """
        if self.paper_trading:
            logger.info(f"[PAPER:Bithumb] 잔고 조회 — {currency}")
            return 0.0
        try:
            accounts: list[dict] = self._get('/v1/accounts')
            # currency 찾기
            target = currency.upper()
            for acc in accounts:
                if acc.get('currency') == target:
                    return float(acc.get('balance', 0))
            return 0.0
        except Exception as e:
            logger.error(f"[Bithumb] 잔고 조회 실패: {e}")
            return None

    def get_all_balances(self) -> dict[str, float]:
        """
        빗썸 전체 잔고 조회.

        Returns:
            {currency: 사용가능잔고} dict
        """
        if self.paper_trading:
            return {}
        try:
            accounts: list[dict] = self._get('/v1/accounts')
            return {
                acc['currency']: float(acc.get('balance', 0))
                for acc in accounts
                if float(acc.get('balance', 0)) > 0
            }
        except Exception as e:
            logger.error(f"[Bithumb] 전체 잔고 조회 실패: {e}")
            return {}

    def buy_market(self, symbol: str, krw_amount: float) -> dict | None:
        """
        빗썸 시장가 매수 (신 API /v1/orders).

        Args:
            symbol: 코인 심볼 (예: "BTC", "DOGE")
            krw_amount: 매수 금액 (원)

        Returns:
            체결 결과 dict 또는 None
        """
        if krw_amount <= 0:
            return None

        if self.paper_trading:
            price = self.get_current_price(symbol)
            if price and price > 0:
                qty = krw_amount / price * (1 - FEE_BITHUMB_TAKER)
                logger.info(
                    f"[PAPER:Bithumb BUY ] {symbol}: {krw_amount:,.0f}원 -> "
                    f"{qty:.6f}개 @ {price:,.0f}원"
                )
                return {
                    "exchange": "bithumb",
                    "side": "buy",
                    "symbol": symbol,
                    "krw_amount": krw_amount,
                    "price": price,
                    "quantity": qty,
                    "fee_pct": FEE_BITHUMB_TAKER,
                    "paper": True,
                }
            return None

        # 실거래 — 빗썸 신 API POST /v1/orders
        try:
            body = {
                "market": f"KRW-{symbol}",
                "side": "bid",           # bid = 매수
                "ord_type": "price",     # price = 시장가 금액 지정
                "price": str(int(krw_amount)),
            }
            order = self._post('/v1/orders', body)
            logger.info(f"[LIVE:Bithumb BUY ] {symbol} {krw_amount:,.0f}원 -> {order}")
            return {"exchange": "bithumb", "side": "buy", "raw": order, "paper": False}
        except Exception as e:
            logger.error(f"[Bithumb] 매수 실패: {e}")
            return None

    def sell_market(self, symbol: str, quantity: float) -> dict | None:
        """
        빗썸 시장가 매도 (신 API /v1/orders).

        Args:
            symbol: 코인 심볼 (예: "BTC", "DOGE")
            quantity: 매도 수량

        Returns:
            체결 결과 dict 또는 None
        """
        if quantity <= 0:
            return None

        if self.paper_trading:
            price = self.get_current_price(symbol)
            if price and price > 0:
                krw_received = quantity * price * (1 - FEE_BITHUMB_TAKER)
                logger.info(
                    f"[PAPER:Bithumb SELL] {symbol}: {quantity:.6f}개 @ {price:,.0f}원 "
                    f"-> {krw_received:,.0f}원"
                )
                return {
                    "exchange": "bithumb",
                    "side": "sell",
                    "symbol": symbol,
                    "quantity": quantity,
                    "price": price,
                    "krw_received": krw_received,
                    "fee_pct": FEE_BITHUMB_TAKER,
                    "paper": True,
                }
            return None

        # 실거래 — 빗썸 신 API POST /v1/orders
        try:
            body = {
                "market": f"KRW-{symbol}",
                "side": "ask",           # ask = 매도
                "ord_type": "market",    # market = 시장가 수량 지정
                "volume": str(round(quantity, 8)),
            }
            order = self._post('/v1/orders', body)
            logger.info(f"[LIVE:Bithumb SELL] {symbol} {quantity:.6f}개 -> {order}")
            return {"exchange": "bithumb", "side": "sell", "raw": order, "paper": False}
        except Exception as e:
            logger.error(f"[Bithumb] 매도 실패: {e}")
            return None

    def cancel_order(self, order_id: str) -> dict | None:
        """
        빗썸 주문 취소 (신 API DELETE /v1/order).

        Args:
            order_id: 취소할 주문 ID (UUID)

        Returns:
            취소 결과 dict 또는 None
        """
        if self.paper_trading:
            logger.info(f"[PAPER:Bithumb] 주문 취소 — {order_id}")
            return {"cancelled": True, "paper": True}
        try:
            result = self._delete('/v1/order', {'uuid': order_id})
            logger.info(f"[LIVE:Bithumb] 주문 취소 -> {result}")
            return result
        except Exception as e:
            logger.error(f"[Bithumb] 주문 취소 실패: {e}")
            return None
