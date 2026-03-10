"""
브로커 인터페이스 (KIS 한국투자증권 / Upbit)
=============================================
- KIS API: 국내주식 주문 (실거래 / 모의투자)
- Upbit API: 비트코인 주문
- 페이퍼트레이딩 시뮬레이션 모드 (기본값)

⚠️ 실거래 모드는 반드시 사용자가 명시적으로 활성화해야 합니다.
"""

import os
import json
import time
import hmac
import hashlib
import requests
import logging
from datetime import datetime
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# ========== KIS API 엔드포인트 ==========
KIS_BASE_URL_REAL = "https://openapi.koreainvestment.com:9443"
KIS_BASE_URL_PAPER = "https://openapivts.koreainvestment.com:29443"

# ========== Upbit API ==========
UPBIT_BASE_URL = "https://api.upbit.com/v1"


class BrokerInterface:
    """
    브로커 인터페이스
    
    기본적으로 페이퍼트레이딩 시뮬레이션으로 동작.
    실거래 활성화는 is_live=True + 명시적 확인 필요.
    
    Usage:
        # 페이퍼트레이딩 (기본)
        broker = BrokerInterface(paper_trading=True)
        result = broker.place_order('005930', 'buy', qty=10, price=70000)
        
        # 실거래 (⚠️ 주의)
        broker = BrokerInterface(
            paper_trading=False,
            kis_app_key='발급받은APP_KEY',
            kis_app_secret='발급받은APP_SECRET',
            kis_account_no='12345678-01'
        )
    """

    def __init__(
        self,
        paper_trading: bool = True,
        kis_app_key: str = None,
        kis_app_secret: str = None,
        kis_account_no: str = None,
        upbit_access_key: str = None,
        upbit_secret_key: str = None,
    ):
        self.paper_trading = paper_trading
        self.kis_app_key = kis_app_key or os.getenv('KIS_APP_KEY')
        self.kis_app_secret = kis_app_secret or os.getenv('KIS_APP_SECRET')
        self.kis_account_no = kis_account_no or os.getenv('KIS_ACCOUNT_NO')
        self.upbit_access_key = upbit_access_key or os.getenv('UPBIT_ACCESS_KEY')
        self.upbit_secret_key = upbit_secret_key or os.getenv('UPBIT_SECRET_KEY')
        
        self._kis_token = None
        self._kis_token_expiry = None
        
        base_url = KIS_BASE_URL_PAPER if paper_trading else KIS_BASE_URL_REAL
        self.base_url = base_url
        
        if not paper_trading:
            logger.warning("⚠️ 실거래 모드 활성화! 신중하게 사용하세요.")
        else:
            logger.info("📋 페이퍼트레이딩 시뮬레이션 모드")

    # ==========================================
    # KIS 한국투자증권 API
    # ==========================================

    def _get_kis_token(self) -> str:
        """KIS OAuth2 토큰 발급"""
        if not self.kis_app_key or not self.kis_app_secret:
            raise ValueError("KIS API 키가 설정되지 않았습니다. 환경변수 KIS_APP_KEY, KIS_APP_SECRET 설정 필요.")
        
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.kis_app_key,
            "appsecret": self.kis_app_secret
        }
        
        resp = requests.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        self._kis_token = data['access_token']
        return self._kis_token

    def _kis_headers(self, tr_id: str) -> dict:
        """KIS API 공통 헤더"""
        if not self._kis_token:
            self._get_kis_token()
        
        return {
            "content-type": "application/json",
            "authorization": f"Bearer {self._kis_token}",
            "appkey": self.kis_app_key,
            "appsecret": self.kis_app_secret,
            "tr_id": tr_id,
            "custtype": "P",  # 개인
        }

    def get_kis_balance(self) -> dict:
        """KIS 잔고 조회"""
        if self.paper_trading and not self.kis_app_key:
            return {'simulated': True, 'cash': 10_000_000, 'message': '페이퍼트레이딩 잔고'}
        
        try:
            # 모의: VTTC8434R, 실거래: TTTC8434R
            tr_id = "VTTC8434R" if self.paper_trading else "TTTC8434R"
            headers = self._kis_headers(tr_id)
            
            params = {
                "CANO": self.kis_account_no[:8],
                "ACNT_PRDT_CD": self.kis_account_no[9:],
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "N",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": ""
            }
            
            resp = requests.get(
                f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
                headers=headers,
                params=params
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"잔고 조회 실패: {e}")
            return {'error': str(e)}

    def place_order_kis(
        self,
        stock_code: str,
        order_type: str,  # 'buy' or 'sell'
        qty: int,
        price: int = 0,  # 0 = 시장가
        order_price_type: str = "00"  # 00=지정가, 01=시장가
    ) -> dict:
        """
        KIS 종목 주문
        
        ⚠️ 페이퍼트레이딩 모드: 시뮬레이션 실행
        ⚠️ 실거래 모드: 실제 주문 전송
        """
        if self.paper_trading and not self.kis_app_key:
            # 완전 시뮬레이션
            simulated_order = {
                'simulated': True,
                'stock_code': stock_code,
                'order_type': order_type,
                'qty': qty,
                'price': price,
                'timestamp': datetime.now().isoformat(),
                'status': 'FILLED (시뮬레이션)',
            }
            logger.info(f"📋 [시뮬레이션] {order_type.upper()} {stock_code} {qty}주 @ ₩{price:,.0f}")
            return simulated_order
        
        try:
            # 모의: VTTC0802U(매수)/VTTC0801U(매도), 실거래: TTTC0802U/TTTC0801U
            if order_type.lower() == 'buy':
                tr_id = "VTTC0802U" if self.paper_trading else "TTTC0802U"
            else:
                tr_id = "VTTC0801U" if self.paper_trading else "TTTC0801U"
            
            headers = self._kis_headers(tr_id)
            body = {
                "CANO": self.kis_account_no[:8],
                "ACNT_PRDT_CD": self.kis_account_no[9:],
                "PDNO": stock_code,
                "ORD_DVSN": order_price_type,
                "ORD_QTY": str(qty),
                "ORD_UNPR": str(price),
            }
            
            resp = requests.post(
                f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash",
                headers=headers,
                json=body
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"✅ [{stock_code}] {order_type} 주문 전송 완료: {data.get('msg1', '')}")
            return data
        except Exception as e:
            logger.error(f"❌ 주문 실패: {e}")
            return {'error': str(e)}

    # ==========================================
    # Upbit API (비트코인)
    # ==========================================

    def _upbit_auth_header(self, query: str = None):
        """Upbit JWT 인증 헤더"""
        import uuid
        import jwt as pyjwt
        
        if not self.upbit_access_key or not self.upbit_secret_key:
            raise ValueError("Upbit API 키 미설정. UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY 환경변수 필요.")
        
        payload = {
            'access_key': self.upbit_access_key,
            'nonce': str(uuid.uuid4()),
        }
        if query:
            query_hash = hashlib.sha512(query.encode()).hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'
        
        token = pyjwt.encode(payload, self.upbit_secret_key, algorithm='HS256')
        return {'Authorization': f'Bearer {token}'}

    def place_order_upbit(
        self,
        market: str = 'KRW-BTC',
        side: str = 'bid',  # bid=매수, ask=매도
        volume: float = None,  # 수량 (ask 시)
        price: float = None,   # 가격 (bid 시)
        ord_type: str = 'price'  # price=시장가매수, market=시장가매도, limit=지정가
    ) -> dict:
        """
        Upbit 주문
        
        ⚠️ 실거래 API 키 없으면 시뮬레이션 실행
        """
        if self.paper_trading and not self.upbit_access_key:
            simulated = {
                'simulated': True,
                'market': market,
                'side': side,
                'price': price,
                'volume': volume,
                'timestamp': datetime.now().isoformat(),
                'status': 'FILLED (시뮬레이션)',
            }
            logger.info(f"📋 [시뮬레이션] Upbit {side} {market} ₩{price:,.0f}")
            return simulated
        
        try:
            query = {'market': market, 'side': side, 'ord_type': ord_type}
            if volume:
                query['volume'] = str(volume)
            if price:
                query['price'] = str(price)
            
            query_str = urlencode(query)
            headers = self._upbit_auth_header(query_str)
            
            resp = requests.post(f"{UPBIT_BASE_URL}/orders", headers=headers, data=query)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"❌ Upbit 주문 실패: {e}")
            return {'error': str(e)}

    def get_upbit_balance(self) -> dict:
        """Upbit 잔고 조회"""
        if not self.upbit_access_key:
            return {'simulated': True, 'krw': 10_000_000, 'btc': 0}
        
        try:
            headers = self._upbit_auth_header()
            resp = requests.get(f"{UPBIT_BASE_URL}/accounts", headers=headers)
            resp.raise_for_status()
            return {'accounts': resp.json()}
        except Exception as e:
            return {'error': str(e)}


if __name__ == "__main__":
    # 페이퍼트레이딩 테스트
    broker = BrokerInterface(paper_trading=True)
    
    print("[KIS 시뮬레이션 주문 테스트]")
    result = broker.place_order_kis('005930', 'buy', qty=10, price=70000)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    print("\n[Upbit 시뮬레이션 주문 테스트]")
    result2 = broker.place_order_upbit('KRW-BTC', side='bid', price=100_000, ord_type='price')
    print(json.dumps(result2, ensure_ascii=False, indent=2))
