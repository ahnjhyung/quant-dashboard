"""
World Bank Open Data Collector
==============================
- API: https://api.worldbank.org/v2/
- API 키 불필요 (완전 공개 API)
- 전 세계 GDP, 무역, 인플레이션, 인구 등 경제 지표
"""

import requests
import time
from typing import Optional

WORLD_BANK_BASE = "https://api.worldbank.org/v2"
WB_RATE_DELAY = 0.2

# 자주 사용하는 지표 코드 목록
WB_INDICATORS = {
    'gdp': 'NY.GDP.MKTP.CD',               # GDP (current US$)
    'gdp_growth': 'NY.GDP.MKTP.KD.ZG',     # GDP growth (%)
    'gdp_per_capita': 'NY.GDP.PCAP.CD',    # GDP per capita
    'inflation': 'FP.CPI.TOTL.ZG',         # Inflation, CPI (%)
    'unemployment': 'SL.UEM.TOTL.ZS',      # Unemployment rate (%)
    'current_account': 'BN.CAB.XOKA.CD',   # Current account balance (US$)
    'exports': 'NE.EXP.GNFS.CD',           # Exports of goods and services
    'imports': 'NE.IMP.GNFS.CD',           # Imports of goods and services
    'trade_balance': 'NE.RSB.GNFS.CD',     # External balance
    'fdi_inflow': 'BX.KLT.DINV.CD.WD',    # FDI, net inflows
    'population': 'SP.POP.TOTL',           # Total population
    'interest_rate': 'FR.INR.RINR',        # Real interest rate
    'stock_market': 'CM.MKT.LCAP.CD',      # Market capitalization
}

# 주요 국가 코드
COUNTRY_CODES = {
    '한국': 'KR', '미국': 'US', '중국': 'CN', '일본': 'JP',
    '독일': 'DE', '영국': 'GB', '프랑스': 'FR', '인도': 'IN',
    '브라질': 'BR', '캐나다': 'CA', '호주': 'AU', '대만': 'TW',
    '세계': 'WLD', 'G7': 'G7', 'OECD': 'OED',
}


class WorldBankCollector:
    """
    World Bank Open Data API 수집기
    
    Usage:
        collector = WorldBankCollector()
        gdp = collector.get_indicator('KR', 'gdp', start=2010, end=2023)
        compare = collector.compare_countries(['KR', 'US', 'CN'], 'gdp_growth')
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'QuantDashboard/1.0'})

    def _get(self, url: str, params: dict = None) -> list:
        """World Bank API 공통 GET (항상 JSON, 페이징 처리)"""
        if params is None:
            params = {}
        params['format'] = 'json'
        params['per_page'] = 1000
        
        all_data = []
        page = 1
        
        while True:
            params['page'] = page
            try:
                resp = self.session.get(url, params=params, timeout=15)
                resp.raise_for_status()
                result = resp.json()
                
                if not isinstance(result, list) or len(result) < 2:
                    break
                
                meta = result[0]
                data = result[1]
                
                if data:
                    all_data.extend(data)
                
                # 페이징 체크    
                total_pages = meta.get('pages', 1)
                if page >= total_pages:
                    break
                page += 1
                time.sleep(WB_RATE_DELAY)
                
            except Exception as e:
                print(f"❌ World Bank API Error: {e}")
                break
        
        return all_data

    def get_indicator(
        self,
        country_code: str,
        indicator_key: str,
        start: int = 2000,
        end: int = 2023
    ) -> list:
        """
        특정 국가의 경제 지표 시계열 데이터
        
        Args:
            country_code: 'KR', 'US', 'CN' 등
            indicator_key: 'gdp', 'gdp_growth', 'inflation' 등 (WB_INDICATORS 참조)
            start: 시작 연도
            end: 끝 연도
            
        Returns:
            [{'year': 2023, 'value': 1.7e12, 'country': 'Korea'}, ...]
        """
        indicator_code = WB_INDICATORS.get(indicator_key, indicator_key)
        url = f"{WORLD_BANK_BASE}/country/{country_code}/indicator/{indicator_code}"
        params = {'date': f"{start}:{end}", 'mrv': 30}
        
        raw = self._get(url, params)
        
        results = []
        for item in raw:
            if item.get('value') is not None:
                results.append({
                    'year': int(item['date']),
                    'value': item['value'],
                    'country': item.get('country', {}).get('value', country_code),
                    'country_code': country_code,
                    'indicator': indicator_key,
                    'indicator_name': item.get('indicator', {}).get('value', ''),
                })
        
        return sorted(results, key=lambda x: x['year'])

    def compare_countries(
        self,
        country_codes: list,
        indicator_key: str,
        start: int = 2000,
        end: int = 2023
    ) -> dict:
        """
        여러 국가의 동일 지표 비교
        
        Returns:
            {'KR': [...], 'US': [...], 'CN': [...]}
        """
        result = {}
        for code in country_codes:
            result[code] = self.get_indicator(code, indicator_key, start, end)
        return result

    def get_korea_dashboard(self) -> dict:
        """
        한국 경제 주요 지표 한 번에 조회
        """
        print("🌏 한국 경제 지표 로딩 중...")
        return {
            'gdp': self.get_indicator('KR', 'gdp', 2010, 2023),
            'gdp_growth': self.get_indicator('KR', 'gdp_growth', 2010, 2023),
            'inflation': self.get_indicator('KR', 'inflation', 2010, 2023),
            'unemployment': self.get_indicator('KR', 'unemployment', 2010, 2023),
            'exports': self.get_indicator('KR', 'exports', 2010, 2023),
            'imports': self.get_indicator('KR', 'imports', 2010, 2023),
            'current_account': self.get_indicator('KR', 'current_account', 2010, 2023),
            'fdi': self.get_indicator('KR', 'fdi_inflow', 2010, 2023),
        }

    def get_global_gdp_ranking(self, year: int = 2022) -> list:
        """
        전 세계 국가별 GDP 순위
        """
        url = f"{WORLD_BANK_BASE}/country/all/indicator/{WB_INDICATORS['gdp']}"
        params = {'date': str(year), 'mrv': 1}
        raw = self._get(url, params)
        
        results = []
        for item in raw:
            if item.get('value') and item.get('countryiso3code'):
                results.append({
                    'country': item.get('country', {}).get('value', ''),
                    'iso3': item.get('countryiso3code', ''),
                    'gdp_usd': item['value'],
                    'year': year
                })
        
        return sorted(results, key=lambda x: -x['gdp_usd'])[:50]

    def search_indicator(self, keyword: str) -> list:
        """
        지표 코드 검색
        """
        url = f"{WORLD_BANK_BASE}/indicator"
        params = {'q': keyword}
        raw = self._get(url, params)
        return raw[:10]


# ==========================================
# STANDALONE TEST
# ==========================================
if __name__ == "__main__":
    collector = WorldBankCollector()
    
    print("[1] 한국 GDP 조회...")
    gdp = collector.get_indicator('KR', 'gdp', 2015, 2023)
    for d in gdp[-3:]:
        print(f"    {d['year']}: ${d['value']:,.0f}")
    
    print("\n[2] 한국/미국/중국 GDP 성장률 비교...")
    comparison = collector.compare_countries(['KR', 'US', 'CN'], 'gdp_growth', 2020, 2023)
    for country, data in comparison.items():
        if data:
            latest = data[-1]
            print(f"    {country}: {latest['year']} → {latest['value']:.1f}%")
