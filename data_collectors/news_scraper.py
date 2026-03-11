"""
뉴스 및 공시 키워드 수집기 (Google News RSS 기반)
=================================================
최근 1일 내 발생한 핵심 키워드(자사주 매입, 유상증자 등)가
포함된 금융 뉴스를 수집합니다.
"""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
from data_collectors.supabase_manager import SupabaseManager

class NewsScraper:
    def __init__(self):
        self.base_url = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
        # event_swing 모듈용 주요 핵심 키워드
        self.keywords = ["자사주 매입", "유상증자"]

    def fetch_recent_events(self) -> list:
        """
        최근 1일 (when:1d) 핵심 이벤트 뉴스를 파싱합니다.
        
        Returns:
            list: [{'company_name': '회사명', 'keyword': '이벤트종류', 'title': '뉴스제목'}]
        """
        results = []
        seen_titles = set()
        
        for k in self.keywords:
            query = f'"{k}" when:1d'
            url = self.base_url.format(query=urllib.parse.quote(query))
            
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as response:
                    xml_data = response.read()
                    
                root = ET.fromstring(xml_data)
                items = root.findall('.//item')
                
                for item in items[:5]:  # 상위 5개만 필터 (중복 방지 등등)
                    title = item.find('title').text
                    
                    if title in seen_titles:
                        continue
                    seen_titles.add(title)
                    
                    # 제목에서 티커(회사명) 파싱 - 휴리스틱 (첫 단어가 보통 회사명인 경우)
                    # ex) "삼성전자, 1조원 자사주 매입 발표 - 매일경제" -> "삼성전자"
                    # "카카오(035720) 유상증자" -> "카카오"
                    
                    match = re.search(r'^\[.*?\]\s*([가-힣A-Za-z0-9]+)', title)
                    if match:
                        company_name = match.group(1)
                    else:
                        company_name = title.split()[0]
                        company_name = re.sub(r'\(.*?\)', '', company_name).strip() # (005930) 제거
                        company_name = re.sub(r'[\,\.\'\"\`\-\+]', '', company_name) # 특수문자 제거
                    
                    if len(company_name) > 1 and len(company_name) <= 10:
                        results.append({
                            'company_name': company_name,
                            'keyword': k,
                            'title': title
                        })
            except Exception as e:
                print(f"[NewsScraper] 실패 {k} : {e}")
                
        # Supabase 적재
        if results:
            mgr = SupabaseManager()
            mgr.insert_news_events(results)
            
        return results

if __name__ == "__main__":
    scraper = NewsScraper()
    events = scraper.fetch_recent_events()
    for e in events:
        print(f"[{e['keyword']}] {e['company_name']} - {e['title']}")
