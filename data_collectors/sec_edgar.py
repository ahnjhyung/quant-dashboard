"""
SEC EDGAR Data Collector
========================
- API 키 불필요: User-Agent HTTP 헤더로 인증
- Rate limit: 초당 최대 10회 (0.1초 간격)
- 공식 문서: https://www.sec.gov/developer
- JSON 기반 XBRL 데이터 파싱 (company_facts API)
"""

import time
import requests
import json
import re
from functools import wraps
from typing import Optional

# ==========================================
# CONFIGURATION
# ==========================================
# SEC EDGAR requires a descriptive User-Agent with contact info
# Format: "CompanyName AppName/Version (contact@email.com)"
SEC_USER_AGENT = "QuantDashboard Personal/1.0 (contact@quant.local)"
SEC_BASE_URL = "https://data.sec.gov"
SEC_SEARCH_URL = "https://efts.sec.gov"
SEC_RATE_LIMIT_DELAY = 0.11  # 초당 ~9회 (안전 마진 포함)

HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate"
    # Host 헤더는 요청 URL에 따라 requests 모듈이 자동 설정하도록 제거함
}

def rate_limited(func):
    """초당 10회 제한 데코레이터"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        time.sleep(SEC_RATE_LIMIT_DELAY)
        return result
    return wrapper


class SECEdgarCollector:
    """
    SEC EDGAR API 데이터 수집기
    
    - api.sec.gov/submissions/ : 기업 제출 목록
    - data.sec.gov/api/xbrl/companyfacts/ : 재무 사실 데이터 (JSON)
    - efts.sec.gov/LATEST/search-index : 문서 전체 검색
    
    Usage:
        collector = SECEdgarCollector()
        cik = collector.ticker_to_cik("AAPL")
        facts = collector.get_company_facts(cik)
        income = collector.get_income_statement(cik)
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        # CIK 매핑 캐시 로드
        self._cik_map: dict = {}
        self._load_cik_map()

    @rate_limited
    def _get(self, url: str, params: dict = None) -> Optional[dict]:
        """공통 GET 요청 (rate limit 적용)"""
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            print(f"[ERROR] SEC EDGAR HTTP Error [{resp.status_code}]: {url}")
            return None
        except Exception as e:
            print(f"[ERROR] SEC EDGAR Error: {e}")
            return None

    def _load_cik_map(self):
        """
        SEC의 전체 ticker→CIK 매핑 파일을 한 번에 다운로드 (캐시)
        https://www.sec.gov/files/company_tickers.json
        """
        try:
            url = "https://www.sec.gov/files/company_tickers.json"
            data = self._get(url)
            if data:
                # 키: 순서번호, 값: {cik_str, ticker, title}
                self._cik_map = {
                    v['ticker'].upper(): str(v['cik_str']).zfill(10)
                    for v in data.values()
                }
                print(f"[OK] SEC EDGAR: {len(self._cik_map)}개 ticker-CIK 매핑 로드 완료")
        except Exception as e:
            print(f"[WARN] SEC CIK 맵 로드 실패: {e}")

    def ticker_to_cik(self, ticker: str) -> Optional[str]:
        """
        티커 심볼 → 10자리 CIK 변환
        예: 'AAPL' → '0000320193'
        """
        cik = self._cik_map.get(ticker.upper())
        if not cik:
            print(f"[WARN] '{ticker}' 티커를 찾을 수 없습니다. SEC에 상장 안 됐을 수 있습니다.")
        return cik

    def get_company_facts(self, cik: str) -> Optional[dict]:
        """
        기업의 전체 XBRL 재무 사실 JSON 반환
        - us-gaap: 미국 GAAP 기준 재무데이터
        - dei: 기업 정체성 정보 (SIC, 회사명 등)
        
        반환 구조: {
            'cik': ...,
            'entityName': 'Apple Inc.',
            'facts': {
                'us-gaap': {
                    'NetIncomeLoss': {'units': {'USD': [...historical...]}}
                }
            }
        }
        """
        url = f"{SEC_BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json"
        data = self._get(url)
        return data

    def get_company_submissions(self, cik: str) -> Optional[dict]:
        """
        기업의 전체 공시 제출 목록 반환 (10-K, 10-Q, 8-K 등)
        """
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        data = self._get(url)
        return data

    def search_filings(self, ticker: str, form_type: str = "10-K", count: int = 5) -> list:
        """
        특정 기업의 특정 공시 유형(10-K, 10-Q, 8-K) 검색
        
        Args:
            ticker: 티커 (예: 'AAPL')
            form_type: 공시 유형 ('10-K', '10-Q', '8-K', '20-F' 등)
            count: 반환 건수
            
        Returns:
            리스트 of dict: [{form, filingDate, reportDate, accessionNumber}, ...]
        """
        cik = self.ticker_to_cik(ticker)
        if not cik:
            return []
        
        submissions = self.get_company_submissions(cik)
        if not submissions:
            return []
        
        recent = submissions.get('filings', {}).get('recent', {})
        forms = recent.get('form', [])
        dates = recent.get('filingDate', [])
        accessions = recent.get('accessionNumber', [])
        reports = recent.get('reportDate', [])
        
        results = []
        for form, date, acc, rep in zip(forms, dates, accessions, reports):
            if form == form_type and len(results) < count:
                results.append({
                    'form': form,
                    'filingDate': date,
                    'reportDate': rep,
                    'accessionNumber': acc,
                    'accessionUrl': f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/",
                })
        return results

    def _extract_financial_series(self, facts: dict, concept: str, unit: str = "USD") -> list:
        """
        company_facts JSON에서 특정 회계 개념의 시계열 데이터 추출
        
        Args:
            facts: get_company_facts() 반환값
            concept: XBRL 개념명 (예: 'NetIncomeLoss', 'Revenues')
            unit: 단위 ('USD', 'shares' 등)
        
        Returns:
            [{'end': '2023-09-30', 'val': 96995000000, 'form': '10-K', ...}, ...]
        """
        try:
            raw = facts['facts']['us-gaap'][concept]['units'][unit]
            # 10-K (연간) 또는 10-Q (분기) 필터
            # accn이 있고 형식이 연간인 것 위주로 정렬
            filtered = [r for r in raw if r.get('form') in ('10-K', '10-Q')]
            # 중복 제거 (같은 end 날짜에 대해 최신 제출본 유지)
            seen = {}
            for r in filtered:
                end = r.get('end', '')
                if end not in seen or r.get('filed', '') > seen[end].get('filed', ''):
                    seen[end] = r
            return sorted(seen.values(), key=lambda x: x.get('end', ''))
        except (KeyError, TypeError):
            return []

    def get_income_statement(self, cik: str) -> dict:
        """
        손익계산서 주요 항목 반환
        
        Returns: {
            'revenue': [...],
            'gross_profit': [...],
            'operating_income': [...],
            'net_income': [...],
            'eps': [...]
        }
        """
        facts = self.get_company_facts(cik)
        if not facts:
            return {}
        
        return {
            'revenue': self._extract_financial_series(facts, 'Revenues'),
            'revenue_alt': self._extract_financial_series(facts, 'RevenueFromContractWithCustomerExcludingAssessedTax'),
            'gross_profit': self._extract_financial_series(facts, 'GrossProfit'),
            'operating_income': self._extract_financial_series(facts, 'OperatingIncomeLoss'),
            'net_income': self._extract_financial_series(facts, 'NetIncomeLoss'),
            'eps_basic': self._extract_financial_series(facts, 'EarningsPerShareBasic', unit='USD/shares'),
            'eps_diluted': self._extract_financial_series(facts, 'EarningsPerShareDiluted', unit='USD/shares'),
            'ebitda': self._extract_financial_series(facts, 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest'),
            'rd_expense': self._extract_financial_series(facts, 'ResearchAndDevelopmentExpense'),
        }

    def get_balance_sheet(self, cik: str) -> dict:
        """
        대차대조표 주요 항목 반환
        
        Returns: {
            'total_assets': [...],
            'total_liabilities': [...],
            'equity': [...],
            'cash': [...],
            'debt_lt': [...],
        }
        """
        facts = self.get_company_facts(cik)
        if not facts:
            return {}
        
        return {
            'total_assets': self._extract_financial_series(facts, 'Assets'),
            'total_liabilities': self._extract_financial_series(facts, 'Liabilities'),
            'equity': self._extract_financial_series(facts, 'StockholdersEquity'),
            'cash': self._extract_financial_series(facts, 'CashAndCashEquivalentsAtCarryingValue'),
            'debt_st': self._extract_financial_series(facts, 'ShortTermBorrowings'),
            'debt_lt': self._extract_financial_series(facts, 'LongTermDebt'),
            'inventory': self._extract_financial_series(facts, 'InventoryNet'),
            'accounts_receivable': self._extract_financial_series(facts, 'AccountsReceivableNetCurrent'),
        }

    def get_cash_flow(self, cik: str) -> dict:
        """현금흐름표 주요 항목 반환"""
        facts = self.get_company_facts(cik)
        if not facts:
            return {}
        
        return {
            'operating_cf': self._extract_financial_series(facts, 'NetCashProvidedByUsedInOperatingActivities'),
            'investing_cf': self._extract_financial_series(facts, 'NetCashProvidedByUsedInInvestingActivities'),
            'financing_cf': self._extract_financial_series(facts, 'NetCashProvidedByUsedInFinancingActivities'),
            'free_cash_flow': self._extract_financial_series(facts, 'FreeCashFlow'),
            'capex': self._extract_financial_series(facts, 'PaymentsToAcquirePropertyPlantAndEquipment'),
        }

    def get_key_metrics(self, ticker: str) -> dict:
        """
        티커 → 종합 재무 지표 (손익 + 대차 + 현금흐름 + 최신값)
        """
        cik = self.ticker_to_cik(ticker)
        if not cik:
            return {'error': f'CIK not found for {ticker}'}
        
        income = self.get_income_statement(cik)
        balance = self.get_balance_sheet(cik)
        cashflow = self.get_cash_flow(cik)
        
        # 최신 연간 수치 추출 헬퍼
        def latest_annual(series: list) -> Optional[float]:
            annual = [x for x in series if x.get('form') == '10-K']
            return annual[-1]['val'] if annual else None
        
        return {
            'ticker': ticker,
            'cik': cik,
            'revenue': latest_annual(income.get('revenue', []) or income.get('revenue_alt', [])),
            'net_income': latest_annual(income.get('net_income', [])),
            'total_assets': latest_annual(balance.get('total_assets', [])),
            'equity': latest_annual(balance.get('equity', [])),
            'operating_cf': latest_annual(cashflow.get('operating_cf', [])),
            'free_cash_flow': latest_annual(cashflow.get('free_cash_flow', [])),
            'income_full': income,
            'balance_full': balance,
            'cashflow_full': cashflow,
        }


# ==========================================
# STANDALONE TEST
# ==========================================
if __name__ == "__main__":
    collector = SECEdgarCollector()
    
    print("\n[1] Apple CIK 조회...")
    cik = collector.ticker_to_cik("AAPL")
    print(f"    AAPL CIK: {cik}")
    
    print("\n[2] 10-K 공시 목록...")
    filings = collector.search_filings("AAPL", form_type="10-K", count=3)
    for f in filings:
        print(f"    {f['filingDate']}: {f['form']} → {f['accessionUrl']}")
    
    print("\n[3] 핵심 재무 지표...")
    metrics = collector.get_key_metrics("AAPL")
    print(f"    Revenue: ${metrics.get('revenue', 0):,.0f}")
    print(f"    Net Income: ${metrics.get('net_income', 0):,.0f}")
    print(f"    OCF: ${metrics.get('operating_cf', 0):,.0f}")
