import os
import requests
from typing import Dict, Any, List
from datetime import datetime
from config import NOTION_API_KEY, NOTION_PARENT_PAGE_ID

class NotionExporter:
    """
    백테스트 성과 지표를 노션(Notion) 페이지로 익스포트하는 모듈
    """
    def __init__(self):
        self.api_key = NOTION_API_KEY
        self.parent_page_id = NOTION_PARENT_PAGE_ID
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

    def create_report_page(self, strategy_name: str, metrics: Dict[str, Any], regime_summary: str = ""):
        """
        새로운 보고서 페이지 생성
        """
        if not self.api_key:
            print("[ERROR] Notion API Key is missing.")
            return None

        url = "https://api.notion.com/v1/pages"
        
        # 1. 페이지 제목 및 부모 설정
        parent = {"page_id": self.parent_page_id} if self.parent_page_id else {"database_id": os.getenv("NOTION_DATABASE_ID", "none")}
        
        if not parent.get("page_id") and parent.get("database_id") == "none":
            print("[WARN] No parent page/database ID found. Reporting might fail.")
            return None

        # 2. 블록 구성
        children = [
            {
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": f"Backtest Report: {strategy_name}"}}]
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"}},
                        {"type": "text", "text": {"content": "Dashboard: "}},
                        {"type": "text", "text": {"content": "Open Local Dashboard", "link": {"url": "http://localhost:8501"}}}
                    ]
                }
            },
            {
                "object": "block",
                "type": "divider",
                "divider": {}
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Portfolio Composition"}}]
                }
            }
        ]

        # Add Weights Info
        weights = metrics.get('Weights', {})
        if weights:
            weight_text = "\n".join([f"• {k}: {v*100:.1f}%" for k, v in weights.items()])
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": weight_text}}]
                }
            })

        children.extend([
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Performance Summary"}}]
                }
            },
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": 
                        f"Total Return: {metrics.get('Total Return', 0)*100:.2f}%\n"
                        f"CAGR: {metrics.get('CAGR', 0)*100:.2f}%\n"
                        f"MDD: {metrics.get('MDD', 0)*100:.2f}%\n"
                        f"Sharpe Ratio: {metrics.get('Sharpe', 0):.2f}\n"
                        f"Calmar Ratio: {metrics.get('Calmar', 0):.2f}"
                    }}],
                    "icon": {"emoji": ">"},
                    "color": "gray_background"
                }
            }
        ])

        # 3. 국면 분석 요약 추가 (있을 경우)
        if regime_summary:
            children.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Market Regime Notes"}}]
                }
            })
            children.append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [{"type": "text", "text": {"content": regime_summary}}]
                }
            })

        payload = {
            "parent": parent,
            "properties": {
                "title": {
                    "title": [{"text": {"content": f"[{datetime.now().strftime('%m%d')}] {strategy_name} Analytics"}}]
                }
            },
            "children": children
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            if response.status_code == 200:
                page_url = response.json().get("url")
                print(f"[OK] Notion report created: {page_url}")
                return page_url
            else:
                print(f"[ERROR] Notion API failed: {response.text}")
                return None
        except Exception as e:
            print(f"[ERROR] Notion export failed: {e}")
            return None

if __name__ == "__main__":
    exporter = NotionExporter()
    test_metrics = {
        "Total Return": 2.5,
        "CAGR": 0.15, 
        "MDD": -0.08, 
        "Sharpe": 1.2, 
        "Calmar": 1.8,
        "Weights": {"SPY": 0.6, "TLT": 0.4}
    }
    exporter.create_report_page("Test Strategy", test_metrics, "Market is in a favorable growth regime.")
