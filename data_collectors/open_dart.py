"""
Open DART (금융감독원 전자공시) 데이터 수집기
============================================
- API: https://opendart.fss.or.kr/
- API 키 필요 (무료 신청: opendart.fss.or.kr)
- 한국 상장기업(코스피/코스닥) 재무제표, 공시 검색
"""

import requests
import time
from typing import Optional
from config import DART_API_KEY

DART_BASE_URL = "https://opendart.fss.or.kr/api"
DART_RATE_DELAY = 0.3  # 초당 3회 이하 권장


class OpenDartCollector:
    """
    금융감독원 Open DART API 수집기
    
    기능:
    - 기업명 → corp_code 변환
    - 재무제표 (단일/연결) 조회
    - 공시 목록 검색
    - 대주주 현황, 배당 정보
    
    Usage:
        collector = OpenDartCollector(api_key="YOUR_KEY")
        corp_code = collector.search_corp("삼성전자")[0]['corp_code']
        statements = collector.get_financial_statements(corp_code, 2023, 4)  # 4분기=연간
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or DART_API_KEY
        if not self.api_key:
            print("⚠️ Open DART API 키가 없습니다. opendart.fss.or.kr에서 무료 신청하세요.")
        self.session = requests.Session()

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """공통 GET 요청"""
        if not self.api_key:
            return {'status': 'ERROR', 'message': 'API 키 없음'}
        
        if params is None:
            params = {}
        params['crtfc_key'] = self.api_key
        
        try:
            resp = self.session.get(
                f"{DART_BASE_URL}/{endpoint}",
                params=params,
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            time.sleep(DART_RATE_DELAY)
            return data
        except Exception as e:
            print(f"❌ Open DART Error [{endpoint}]: {e}")
            return None

    def search_corp(self, company_name: str) -> list:
        """
        기업명으로 corp_code 검색
        
        Returns:
            [{'corp_code': '00126380', 'corp_name': '삼성전자', 'stock_code': '005930', ...}]
        """
        # DART는 기업 전체 목록을 ZIP 파일로 제공 (별도 처리 필요)
        # 간편하게 공시 검색 API를 활용하여 기업 조회
        data = self._get("list.json", {
            'corp_cls': 'Y',  # Y=유가증권(코스피), K=코스닥
            'bgn_de': '20240101',
            'end_de': '20241231',
            'corp_name': company_name,
            'page_no': 1,
            'page_count': 10
        })
        
        if not data or data.get('status') != '000':
            return []
        
        # 기업명 기준으로 unique 목록 추출
        seen = {}
        for item in data.get('list', []):
            cn = item.get('corp_name', '')
            if cn not in seen:
                seen[cn] = {
                    'corp_code': item.get('corp_code', ''),
                    'corp_name': cn,
                    'stock_code': item.get('stock_code', ''),
                    'corp_cls': item.get('corp_cls', ''),
                }
        return list(seen.values())

    def get_company_info(self, corp_code: str) -> Optional[dict]:
        """
        기업 기본 정보 조회
        
        Returns:
            {국문명, 영문명, 설립일, 결산월, 대표자명, 업종코드, 홈페이지, ...}
        """
        data = self._get("company.json", {'corp_code': corp_code})
        if data and data.get('status') == '000':
            return data
        return None

    def get_financial_statements(
        self,
        corp_code: str,
        year: int,
        quarter: int = 4,
        fs_div: str = "OFS"
    ) -> Optional[dict]:
        """
        재무제표 조회
        
        Args:
            corp_code: 고유번호 (8자리)
            year: 사업연도 (예: 2023)
            quarter: 1분기=1, 반기=2, 3분기=3, 사업연도=4
            fs_div: 'OFS'=재무제표(별도), 'CFS'=연결재무제표
            
        Returns:
            {
                'income_statement': [...],
                'balance_sheet': [...],
                'cash_flow': [...]
            }
        """
        reprt_map = {1: '11013', 2: '11012', 3: '11014', 4: '11011'}
        reprt_code = reprt_map.get(quarter, '11011')
        
        # 재무제표 유형별 조회
        def fetch(sj_div):
            return self._get("fnlttSinglAcntAll.json", {
                'corp_code': corp_code,
                'bsns_year': str(year),
                'reprt_code': reprt_code,
                'fs_div': fs_div,
            })
        
        raw = fetch('CFS')
        if not raw or raw.get('status') != '000':
            raw = fetch('OFS')
        
        if not raw or raw.get('status') != '000':
            return {'error': f"데이터 없음: {raw.get('message') if raw else '연결 실패'}"}
        
        items = raw.get('list', [])
        
        # 계정과목별 분류
        bs_accounts = ['자산총계', '부채총계', '자본총계', '유동자산', '비유동자산', '유동부채', '비유동부채']
        is_accounts = ['매출액', '영업이익', '당기순이익', '법인세비용차감전순이익', '매출총이익']
        cf_accounts = ['영업활동으로인한현금흐름', '투자활동으로인한현금흐름', '재무활동으로인한현금흐름']
        
        balance_sheet = [i for i in items if i.get('account_nm', '') in bs_accounts]
        income_statement = [i for i in items if i.get('account_nm', '') in is_accounts]
        cash_flow = [i for i in items if any(k in i.get('account_nm', '') for k in cf_accounts)]
        
        return {
            'corp_code': corp_code,
            'year': year,
            'quarter': quarter,
            'fs_div': fs_div,
            'balance_sheet': balance_sheet,
            'income_statement': income_statement,
            'cash_flow': cash_flow,
            'all_items': items[:50]  # 전체 50개 항목
        }

    def get_disclosure_list(self, corp_code: str, bgn_de: str = "20240101", count: int = 20) -> list:
        """
        최근 공시 목록 조회
        
        Returns:
            [{rcept_dt, corp_name, report_nm, rcept_no, ...}]
        """
        from datetime import datetime
        end_de = datetime.now().strftime("%Y%m%d")
        
        data = self._get("list.json", {
            'corp_code': corp_code,
            'bgn_de': bgn_de,
            'end_de': end_de,
            'page_count': count
        })
        
        if data and data.get('status') == '000':
            return data.get('list', [])
        return []

    def get_dividend_info(self, corp_code: str, year: int) -> Optional[dict]:
        """배당 정보 조회"""
        data = self._get("alotMatter.json", {
            'corp_code': corp_code,
            'bsns_year': str(year),
            'reprt_code': '11011',  # 사업보고서
        })
        if data and data.get('status') == '000':
            return data.get('list', [])
        return []

    def get_major_shareholders(self, corp_code: str, year: int) -> list:
        """5% 이상 대주주 현황"""
        data = self._get("majorstock.json", {
            'corp_code': corp_code,
            'bsns_year': str(year),
            'reprt_code': '11011',
        })
        if data and data.get('status') == '000':
            return data.get('list', [])
        return []


    def get_cb_refixing_notices(self, corp_code: str, bgn_de: str = "20240101") -> list:
        """
        전환사채(CB) 전환가액 조정(리픽싱) 공시 검색
        
        - '전환가액의조정' 키워드가 포함된 공시 필터링
        - 리픽싱은 주가 하락 시 발생하며, 전환가가 낮아지면 향후 주가 반등 시 수익 기대값이 높음
        """
        notices = self.get_disclosure_list(corp_code, bgn_de, count=100)
        refix_notices = [
            n for n in notices 
            if '전환가액' in n.get('report_nm', '') and '조정' in n.get('report_nm', '')
        ]
        return refix_notices

# ==========================================
# STANDALONE TEST
# ==========================================
if __name__ == "__main__":
    collector = OpenDartCollector()
    
    print("[1] 삼성전자 검색...")
    corps = collector.search_corp("삼성전자")
    for c in corps[:3]:
        print(f"    {c}")
    
    if corps:
        corp_code = corps[0]['corp_code']
        print(f"\n[2] 재무제표 조회 (2023년)...")
        stmt = collector.get_financial_statements(corp_code, 2023)
        if stmt and 'income_statement' in stmt:
            for item in stmt['income_statement']:
                print(f"    {item.get('account_nm')}: {item.get('thstrm_amount')}")
