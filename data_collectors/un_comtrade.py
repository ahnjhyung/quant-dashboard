"""
UN Comtrade 국제 무역 데이터 수집기
=====================================
- API: https://comtradeapi.un.org/
- 신규 API v2 사용 (2023년 이후)
- 무료 Tier: 월 500건, 초당 1건 (구독 시 확장 가능)
- 키 없이 Preview API로 일부 데이터 조회 가능
"""

import requests
import time
from typing import Optional
from config import UN_COMTRADE_API_KEY

COMTRADE_API_KEY = UN_COMTRADE_API_KEY
COMTRADE_BASE_URL = "https://comtradeapi.un.org/data/v1"
COMTRADE_PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview"
COMTRADE_RATE_DELAY = 1.0  # 초당 1건 이하 (free tier)

# UN Comtrade 국가 코드 (M49)
COMTRADE_COUNTRIES = {
    '한국': '410', '미국': '842', '중국': '156', '일본': '392',
    '독일': '276', '대만': '158', '베트남': '704', '인도': '356',
    '홍콩': '344', '세계전체': '0',
}

# 무역 흐름 코드
TRADE_FLOWS = {
    'X': '수출(Export)',
    'M': '수입(Import)',
    'RX': '재수출(Re-export)',
    'RM': '재수입(Re-import)',
}

# HS 분류 버전
HS_CLASSIFICATIONS = ['HS', 'H0', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6']


class UNComtradeCollector:
    """
    UN Comtrade 국제 무역 통계 수집기
    
    - reporters: 신고국 (데이터 제출국)
    - partners: 파트너국 (교역 상대국)
    - cmdCode: HS 코드 (품목)
    - flowCode: X(수출) / M(수입)
    
    API 키 없이는 Preview API (한정 데이터) 사용 가능
    
    Usage:
        collector = UNComtradeCollector(api_key="YOUR_KEY")
        data = collector.get_trade_flows(
            reporter='410',  # 한국
            partner='842',   # 미국
            hs_code='8542',  # 반도체
            year=2022
        )
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or COMTRADE_API_KEY
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'QuantDashboard/1.0',
            'Accept': 'application/json',
        })
        if self.api_key:
            self.session.headers['Ocp-Apim-Subscription-Key'] = self.api_key
            print("[UN Comtrade] API Key Set")
        else:
            print("[UN Comtrade] No API Key. Using Preview API (Limited)")

    def _get(self, url: str, params: dict = None) -> Optional[dict]:
        """공통 GET 요청"""
        try:
            resp = self.session.get(url, params=params, timeout=20)
            time.sleep(COMTRADE_RATE_DELAY)
            
            if resp.status_code == 401:
                print("❌ UN Comtrade: API 키 인증 실패")
                return None
            elif resp.status_code == 429:
                print("⚠️ UN Comtrade: Rate limit 도달. 60초 대기...")
                time.sleep(60)
                return self._get(url, params)
            
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"❌ UN Comtrade Error: {e}")
            return None

    def get_trade_flows(
        self,
        reporter: str,
        partner: str = "0",
        hs_code: str = "TOTAL",
        year: int = 2022,
        flow: str = "X",
        classification: str = "HS"
    ) -> list:
        """
        특정 국가 간 무역 흐름 조회
        
        Args:
            reporter: 신고국 코드 (예: '410'=한국, '842'=미국)
            partner: 파트너국 코드 ('0'=세계 전체)
            hs_code: HS 코드 (예: '8542', 'TOTAL'=전체)
            year: 연도
            flow: 'X'=수출, 'M'=수입
            classification: 'HS', 'H6' 등
            
        Returns:
            [{'reporterCode': '410', 'cmdCode': '8542', 'primaryValue': 1.23e11, ...}]
        """
        if self.api_key:
            url = f"{COMTRADE_BASE_URL}/get"
            params = {
                'reporterCode': reporter,
                'partnerCode': partner,
                'cmdCode': hs_code,
                'period': str(year),
                'flowCode': flow,
                'typeCode': 'C',
                'freqCode': 'A',  # Annual
                'clCode': classification,
            }
        else:
            # Preview API (키 없이 사용 가능, 100건 제한)
            url = f"{COMTRADE_PREVIEW_URL}/C/A/{year}/{flow}/{classification}/{reporter}/{hs_code}/{partner}/0"
            params = {}
        
        data = self._get(url, params)
        if not data:
            return []
        
        # 데이터 구조 정규화
        records = data.get('data', data) if isinstance(data, dict) else data
        if not isinstance(records, list):
            return []
        
        results = []
        for r in records:
            results.append({
                'reporter': r.get('reporterDesc', r.get('reporterCode', reporter)),
                'partner': r.get('partnerDesc', r.get('partnerCode', partner)),
                'hs_code': r.get('cmdCode', hs_code),
                'commodity': r.get('cmdDesc', ''),
                'year': r.get('period', year),
                'flow': r.get('flowDesc', flow),
                'value_usd': r.get('primaryValue', r.get('tradeValue', 0)),
                'quantity': r.get('qty', None),
                'quantity_unit': r.get('qtyUnitAbbr', ''),
                'net_weight_kg': r.get('netWgt', None),
            })
        
        return results

    def get_korea_major_exports(self, year: int = 2022) -> dict:
        """
        한국의 주요 수출 품목별 데이터
        
        Returns:
            {'반도체': [...], '자동차': [...], '석유화학': [...]}
        """
        hs_codes = {
            '반도체': '8542',
            '자동차': '8703',
            '석유제품': '2710',
            '선박': '8901',
            '디스플레이': '9013',
        }
        
        results = {}
        for product, hs in hs_codes.items():
            print(f"  → {product} (HS {hs}) 조회 중...")
            data = self.get_trade_flows('410', '0', hs, year, 'X')
            results[product] = data
            time.sleep(COMTRADE_RATE_DELAY)
        
        return results

    def get_global_commodity_trade(self, hs_code: str, year: int = 2022, top_n: int = 20) -> dict:
        """
        특정 품목의 전 세계 최대 수출국/수입국 조회
        
        Returns:
            {'exporters': [...상위 수출국], 'importers': [...상위 수입국]}
        """
        results = {'exporters': [], 'importers': [], 'hs_code': hs_code, 'year': year}
        
        # 전 세계 수출 데이터 (reporter=ALL → 개별 요청이 필요)
        # Free tier 한계로 주요 국가만 조회
        major_reporters = ['842', '156', '276', '410', '392', '826', '250', '124', '356', '036']
        
        for reporter in major_reporters[:5]:  # Rate limit 고려
            exp = self.get_trade_flows(reporter, '0', hs_code, year, 'X')
            if exp:
                results['exporters'].extend(exp)
            imp = self.get_trade_flows(reporter, '0', hs_code, year, 'M')
            if imp:
                results['importers'].extend(imp)
        
        # 금액 기준 정렬
        results['exporters'] = sorted(results['exporters'], key=lambda x: -(x.get('value_usd') or 0))[:top_n]
        results['importers'] = sorted(results['importers'], key=lambda x: -(x.get('value_usd') or 0))[:top_n]
        
        return results

    def get_bilateral_trade(
        self,
        country1_code: str,
        country2_code: str,
        year: int = 2022
    ) -> dict:
        """
        두 국가 간 양자 무역 현황
        
        Returns:
            {
                'exports_1to2': [...],  # country1 → country2 수출
                'exports_2to1': [...],  # country2 → country1 수출 (= country1 수입)
            }
        """
        return {
            'exports': self.get_trade_flows(country1_code, country2_code, 'TOTAL', year, 'X'),
            'imports': self.get_trade_flows(country1_code, country2_code, 'TOTAL', year, 'M'),
        }

    def list_reporters(self) -> list:
        """사용 가능한 신고국 코드 목록 조회"""
        url = "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get('results', [])
        except Exception as e:
            print(f"❌ Reporters 조회 실패: {e}")
            return []


if __name__ == "__main__":
    collector = UNComtradeCollector()
    
    print("[1] 한국→미국 수출 조회 (2022년 반도체)...")
    data = collector.get_trade_flows('410', '842', '8542', 2022, 'X')
    for d in data[:3]:
        print(f"    {d['reporter']} → {d['partner']}: ${d['value_usd']:,.0f} USD")
    
    print("\n[2] 한미 양자무역...")
    bilateral = collector.get_bilateral_trade('410', '842', 2022)
    if bilateral['exports']:
        e = bilateral['exports'][0]
        print(f"    한국→미국 수출: ${e.get('value_usd', 0):,.0f} USD")
