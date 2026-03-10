"""
Notion Reporter
===============
Supabase의 퀀트 분석 결과와 매크로 지표를 읽어서
노션에 데일리 리포트 페이지를 생성하는 모듈 (GAS 이메일 포맷 완벽 재현)
"""

import os
from datetime import datetime
from notion_client import Client
from config import NOTION_API_KEY, NOTION_PARENT_PAGE_ID, NOTION_DATABASE_ID
from data_collectors.supabase_manager import SupabaseManager

class NotionReporter:
    def __init__(self):
        if not NOTION_API_KEY:
            self.client = None
            print("[WARN] [NotionReporter] NOTION_API_KEY가 설정되지 않아 비활성화됩니다.")
        else:
            self.client = Client(auth=NOTION_API_KEY)
            
        self.db = SupabaseManager()
        self.parent_page_id = NOTION_PARENT_PAGE_ID
        self.database_id = NOTION_DATABASE_ID
        
        if not self.parent_page_id:
            print("[WARN] [NotionReporter] NOTION_PARENT_PAGE_ID가 설정되지 않았습니다.")

    def setup_dashboard(self):
        """대시보드 세팅: 기존 블록 초기화 및 2단 위젯 + 새로운 데일리 데이터베이스 생성"""
        if not self.client or not self.parent_page_id:
            return None

        print("[NotionReporter] 기존 페이지 초기화 중...")
        children = self.client.blocks.children.list(block_id=self.parent_page_id).get('results', [])
        for block in children:
            try:
                self.client.blocks.delete(block_id=block['id'])
            except:
                pass

        print("[NotionReporter] 대시보드 위젯(뉴스+금융 정보 링크) 생성 중...")
        widget_blocks = [
            {
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": "📈 통합 퀀트 대시보드"}}]
                }
            },
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": "매일 아침 8시(KST) 자동 갱신되는 전문가 수준의 데일리 퀀트 브리핑 아카이브입니다.\n아래 표의 최신 항목(Row)을 열어 상세 브리핑을 확인하세요."}}],
                    "icon": {"emoji": "💡"}
                }
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "🌐 주요 금융/마켓 위젯"}}]
                }
            },
            {
                "object": "block",
                "type": "column_list",
                "column_list": {
                    "children": [
                        {
                            "object": "block",
                            "type": "column",
                            "column": {
                                "children": [
                                    {
                                        "object": "block",
                                        "type": "bookmark",
                                        "bookmark": {"url": "https://kr.investing.com/economic-calendar/"}
                                    }
                                ]
                            }
                        },
                        {
                            "object": "block",
                            "type": "column",
                            "column": {
                                "children": [
                                    {
                                        "object": "block",
                                        "type": "bookmark",
                                        "bookmark": {"url": "https://alternative.me/crypto/fear-and-greed-index/"}
                                    }
                                ]
                            }
                        }
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
                    "rich_text": [{"type": "text", "text": {"content": "📚 데일리 브리핑 데이터베이스"}}]
                }
            }
        ]
        
        self.client.blocks.children.append(
            block_id=self.parent_page_id,
            children=widget_blocks
        )
        
        print("[NotionReporter] Creating new Daily Quant Reports database...")
        db_response = self.client.databases.create(
            parent={"type": "page_id", "page_id": self.parent_page_id},
            title=[{"type": "text", "text": {"content": "Daily Quant Reports"}}],
            properties={
                "Name": {
                    "title": {}
                },
                "Report Date": {
                    "date": {}
                },
                "VIX": {
                    "number": {
                        "format": "number"
                    }
                },
                "Strategy": {
                    "select": {
                        "options": [
                           {"name": "NORMAL", "color": "blue"},
                           {"name": "DEFENSE", "color": "red"}
                        ]
                    }
                }
            }
        )
        
        db_id = db_response['id']
        print(f"[OK] Dashboard Setup Complete! DB ID: {db_id}")
        import time
        print("Waiting 10 seconds for Notion to index properties...")
        time.sleep(10)
        
        # .env 파일에 자동 추가하여 다음에 불러올 수 있도록 처리
        try:
            with open(".env", "a", encoding="utf-8") as f:
                f.write(f"\nNOTION_DATABASE_ID={db_id}\n")
            print(".env 파일에 NOTION_DATABASE_ID 등록 성공")
        except Exception as e:
            print(f".env 파일 기록 실패: {e}")
            
        self.database_id = db_id
        return db_id

    def create_daily_report(self):
        """GAS 이메일 리포트 양식을 본딴 노션 대시보드 리포트 생성"""
        if not self.client or not self.parent_page_id:
            return None

        # 새로 도입된 Database ID 로직 확인
        if not self.database_id:
            print("[WARN] NOTION_DATABASE_ID가 누락되어 구조를 처음부터 셋업합니다.")
            self.setup_dashboard()
            
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # 1. 데이터 로드
        recent_assets = self.db.get_recent_high_ev_assets(limit=10)
        macro_dict = self.db.get_latest_macro()
        rag_text = self.db.get_latest_rag_insight()

        # 데이터 파싱 헬퍼 함수
        def get_macro(ticker, is_prev=False):
            data = macro_dict.get(ticker, {})
            val = data.get("prev") if is_prev else data.get("current")
            try:
                return float(val) if val is not None else 0.0
            except:
                return 0.0

        def get_asset_price(symbol):
            if not recent_assets: return 0.0
            for a in recent_assets:
                if a.get("symbol") == symbol:
                    try:
                        return float(a.get("close_price", 0))
                    except:
                        return 0.0
            return 0.0

        # 지표 연산
        kr_rate = get_macro('KR_BASE_RATE')
        us_rate = get_macro('FEDFUNDS') or get_macro('DGS2')
        rate_diff = kr_rate - us_rate

        cpi = get_macro('CPALTT01USM657N')
        pce = get_macro('PCEPI')

        btc_price = get_asset_price('BTC-USD')
        gold_price = get_asset_price('GC=F')
        sp500_price = get_asset_price('^GSPC')

        fx_rate = get_macro('DEXKOUS')
        fx_prev = get_macro('DEXKOUS', is_prev=True) or fx_rate
        fx_change = fx_rate - fx_prev
        fx_arrow = "🔺" if fx_change > 0 else "🔻" if fx_change < 0 else "-"

        vix = get_macro('VIXCLS')
        vix_prev = get_macro('VIXCLS', is_prev=True) or vix
        vix_change = vix - vix_prev
        vix_arrow = "🔺" if vix_change > 0 else "🔻" if vix_change < 0 else "-"

        t10y2y = get_macro('T10Y2Y')
        ted_rate = get_macro('TEDRATE')
        fsi = get_macro('STLFSI3')
        unrate = get_macro('UNRATE')
        m2 = get_macro('M2SL')
        nfci = get_macro('NFCI')

        tga = get_macro('WTREGEN') / 1000 if get_macro('WTREGEN') else 0
        rrp = get_macro('RRPONTSYD')
        fed_assets = get_macro('WALCL') / 1000 if get_macro('WALCL') else 0
        net_liq = (fed_assets - tga - rrp) if fed_assets > 0 else 0

        tga_prev = get_macro('WTREGEN', True) / 1000 if get_macro('WTREGEN', True) else 0
        rrp_prev = get_macro('RRPONTSYD', True)
        fed_assets_prev = get_macro('WALCL', True) / 1000 if get_macro('WALCL', True) else 0
        net_liq_prev = (fed_assets_prev - tga_prev - rrp_prev) if fed_assets_prev > 0 else 0
        
        liq_change = net_liq - net_liq_prev
        liq_arrow = "🔺" if liq_change > 0 else "🔻" if liq_change < 0 else "-"

        high_yield = get_macro('BAMLH0A0HYM2EY') or get_macro('BAMLH0A0HYM2')

        strat_mode = "DEFENSE (Crisis)" if vix > 25 else "NORMAL (Accumulate)"
        liquidity_status = "위험(유동성흡수)" if (0 < net_liq < 6000) else "양호(유동성공급)"
        if net_liq == 0:
            liquidity_status = "데이터 파싱 대기중"

        # 2. 노션 블록(본문) 구성
        blocks = []

        # [상단 대시보드 콜아웃]
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [
                    {"type": "text", "text": {"content": "CURRENT STRATEGY\n"}, "annotations": {"bold": True, "color": "red" if vix > 25 else "blue"}},
                    {"type": "text", "text": {"content": f"🔥 {strat_mode}\n"}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": f"💧 유동성 상태: {liquidity_status}"}, "annotations": {"color": "gray"}}
                ],
                "icon": {"emoji": "🚨" if vix > 25 else "📊"},
                "color": "red_background" if vix > 25 else "blue_background"
            }
        })
        blocks.append({"object": "block", "type": "divider", "divider": {}})

        # 섹션 1: 주요 자산 동향
        blocks.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "📊 주요 자산 동향 (Prices)"}}]}
        })

        asset_rows = [
            {
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": "비트코인 (BTC)"}}],
                        [{"type": "text", "text": {"content": f"${btc_price:,.0f}" if btc_price > 0 else "-"}}],
                        [{"type": "text", "text": {"content": "금 (Gold)"}}],
                        [{"type": "text", "text": {"content": f"${gold_price:,.0f}" if gold_price > 0 else "-"}}],
                        [{"type": "text", "text": {"content": "S&P 500"}}],
                        [{"type": "text", "text": {"content": f"{sp500_price:,.2f}" if sp500_price > 0 else "-"}}]
                    ]
                }
            }
        ]

        added = 0
        if recent_assets:
            for asset in recent_assets:
                if added >= 2: break
                symbol = str(asset.get("symbol", ""))
                ev_score = asset.get("ev_score")
                price = str(asset.get("close_price", "-"))
                
                # EV가 명시되어 있는(매크로, 지수 제외) 실제 종목만 필터링
                if ev_score is not None and symbol not in ['BTC-USD', 'GC=F', '^GSPC'] and symbol:
                    ev = str(ev_score)
                    asset_rows.append({
                        "type": "table_row",
                        "table_row": {
                            "cells": [
                                [{"type": "text", "text": {"content": f"추천: {symbol}"}}],
                                [{"type": "text", "text": {"content": f"EV. {ev}"}, "annotations": {"color": "orange"}}],
                                [{"type": "text", "text": {"content": "가격"}}],
                                [{"type": "text", "text": {"content": f"${price}" if price != "-" else "-"}}],
                                [{"type": "text", "text": {"content": "-"}}],
                                [{"type": "text", "text": {"content": "-"}}]
                            ]
                        }
                    })
                    added += 1

        blocks.append({
            "object": "block",
            "type": "table",
            "table": {
                "table_width": 6,
                "has_column_header": False,
                "has_row_header": False,
                "children": asset_rows
            }
        })
        blocks.append({"object": "block", "type": "divider", "divider": {}})

        # 섹션 2: 매크로 대시보드
        blocks.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "🌐 핵심 경제 지표 대시보드 (최근 대비 변동)"}}]}
        })

        macro_rows = [
            {
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": "한국 금리"}}],
                        [{"type": "text", "text": {"content": f"{kr_rate}%"}}],
                        [{"type": "text", "text": {"content": "미국 금리"}}],
                        [{"type": "text", "text": {"content": f"{us_rate}%"}}],
                        [{"type": "text", "text": {"content": "한미 금리차"}}],
                        [{"type": "text", "text": {"content": f"{rate_diff:.2f}%p"}, "annotations": {"color": "red" if rate_diff < 0 else "blue"}}]
                    ]
                }
            },
            {
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": "USD/KRW 환율"}}],
                        [
                            {"type": "text", "text": {"content": f"{fx_rate} "}},
                            {"type": "text", "text": {"content": f" ({fx_arrow}{abs(fx_change):.1f})"}, "annotations": {"color": "gray", "italic": True}}
                        ],
                        [{"type": "text", "text": {"content": "순유동성(B)"}}],
                        [
                            {"type": "text", "text": {"content": f"${round(net_liq):,} "}},
                            {"type": "text", "text": {"content": f" ({liq_arrow}{abs(round(liq_change))})"}, "annotations": {"color": "gray", "italic": True}}
                        ],
                        [{"type": "text", "text": {"content": "VIX 공포지수"}}],
                        [
                            {"type": "text", "text": {"content": f"{vix} "}, "annotations": {"color": "red" if vix > 20 else "default"}},
                            {"type": "text", "text": {"content": f" ({vix_arrow}{abs(vix_change):.2f})"}, "annotations": {"color": "gray", "italic": True}}
                        ]
                    ]
                }
            },
            {
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": "TGA 잔고(B)"}}],
                        [{"type": "text", "text": {"content": f"${round(tga):,}"}}],
                        [{"type": "text", "text": {"content": "RRP 역레포(B)"}}],
                        [{"type": "text", "text": {"content": f"${round(rrp):,}"}}],
                        [{"type": "text", "text": {"content": "Fed 자산(B)"}}],
                        [{"type": "text", "text": {"content": f"${round(fed_assets):,}"}}]
                    ]
                }
            },
            {
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": "HY 실효금리"}}],
                        [{"type": "text", "text": {"content": f"{high_yield}%"}}],
                        [{"type": "text", "text": {"content": "미국 CPI"}}],
                        [{"type": "text", "text": {"content": f"{cpi:.2f}%"}}],
                        [{"type": "text", "text": {"content": "통원 물가(PCE)"}}],
                        [{"type": "text", "text": {"content": f"{pce:.2f}"}}]
                    ]
                }
            },
            {
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": "장단기금리차"}}],
                        [{"type": "text", "text": {"content": f"{t10y2y:.2f}%p"}, "annotations": {"color": "red" if t10y2y < 0 else "blue"}}],
                        [{"type": "text", "text": {"content": "금융스트레스"}}],
                        [{"type": "text", "text": {"content": f"{fsi:.2f}"}}],
                        [{"type": "text", "text": {"content": "TED스프레드"}}],
                        [{"type": "text", "text": {"content": f"{ted_rate:.2f}%"}}]
                    ]
                }
            },
            {
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": "실업률(UNRATE)"}}],
                        [{"type": "text", "text": {"content": f"{unrate:.1f}%"}}],
                        [{"type": "text", "text": {"content": "M2 통화량"}}],
                        [{"type": "text", "text": {"content": f"${m2:,.0f} B" if m2 > 0 else "-"}}],
                        [{"type": "text", "text": {"content": "시카고 NFCI"}}],
                        [{"type": "text", "text": {"content": f"{nfci:.2f}"}}]
                    ]
                }
            }
        ]

        blocks.append({
            "object": "block",
            "type": "table",
            "table": {
                "table_width": 6,
                "has_column_header": False,
                "has_row_header": False,
                "children": macro_rows
            }
        })
        blocks.append({"object": "block", "type": "divider", "divider": {}})

        # 섹션 3: AI Analyst Insight
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "🧠 AI Analyst Insight"}, "annotations": {"color": "blue"}}]}
        })

        # 가독성을 위해 빈 줄 생성 도우미 함수 
        empty_line_block = {"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}}

        if rag_text:
            lines = rag_text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 수평선 처리
                if line.startswith('---'):
                    blocks.append({"object": "block", "type": "divider", "divider": {}})
                    blocks.append(empty_line_block.copy())
                    continue
                
                # 헤딩 처리
                if line.startswith('###'):
                    blocks.append({
                        "object": "block",
                        "type": "heading_3",
                        "heading_3": {"rich_text": [{"type": "text", "text": {"content": line.replace('#', '').strip()}}]}
                    })
                    continue
                elif line.startswith('##'):
                    blocks.append({
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {"rich_text": [{"type": "text", "text": {"content": line.replace('#', '').strip()}}]}
                    })
                    continue

                # 핵심 요약 (주황색 콜아웃)
                if "[핵심 요약]" in line:
                    blocks.append({
                        "object": "block",
                        "type": "callout",
                        "callout": {
                            "rich_text": [{"type": "text", "text": {"content": "핵심 요약"}, "annotations": {"bold": True, "color": "orange"}}],
                            "icon": {"emoji": "📌"},
                            "color": "orange_background"
                        }
                    })
                    blocks.append(empty_line_block.copy())
                    continue

                if line.startswith('A.') or line.startswith('B.') or line.startswith('C.') or line.startswith('1.') or line.startswith('2.') or line.startswith('3.') or line.startswith('4.'):
                    blocks.append(empty_line_block.copy())  # 번호 매기기, 알파벳 단락 위 빈 줄 추가
                    blocks.append({
                        "object": "block",
                        "type": "heading_3",
                        "heading_3": {"rich_text": [{"type": "text", "text": {"content": line}, "annotations": {"color": "blue", "bold": True}}]}
                    })
                    continue

                # 리스트 아이템
                if line.startswith('- ') or line.startswith('* '):
                    # 볼드 파싱
                    item_text = line[2:]
                    rich_text = []
                    parts = item_text.split('**')
                    for i, part in enumerate(parts):
                        if i % 2 == 1:
                            rich_text.append({"type": "text", "text": {"content": part}, "annotations": {"bold": True}})
                        else:
                            if part: rich_text.append({"type": "text", "text": {"content": part}})

                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": rich_text}
                    })
                    blocks.append(empty_line_block.copy()) # 가독성 한줄 추가
                    continue

                # 기본 단락 (Paragraph) with Bold text parsing
                rich_text = []
                parts = line.split('**')
                for i, part in enumerate(parts):
                    if i % 2 == 1:
                        rich_text.append({"type": "text", "text": {"content": part}, "annotations": {"bold": True}})
                    else:
                        if part: rich_text.append({"type": "text", "text": {"content": part}})
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": rich_text}
                })
                # 가독성을 위해 단락 하나당 빈줄 하나 추가
                blocks.append(empty_line_block.copy())
        else:
            blocks.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": "오늘 생성된 AI 브리핑 데이터가 없습니다. (RAG 파이프라인 미실행)"}}],
                    "icon": {"emoji": "⚠️"}
                }
            })

        # 3. 노션 데이터베이스 Row(페이지) 생성 API 호출
        try:
            print(f"[NotionReporter] Inserting report into DB: {self.database_id}")
            new_page = self.client.pages.create(
                parent={"type": "database_id", "database_id": self.database_id},
                properties={
                    "Name": {
                        "title": [
                            {"type": "text", "text": {"content": f"📊 Daily 브리핑 ({today_str})"}}
                        ]
                    },
                    "Report Date": {
                        "date": {"start": today_str}
                    },
                    "VIX": {
                        "number": vix
                    },
                    "Strategy": {
                        "select": {"name": "DEFENSE" if vix > 25 else "NORMAL"}
                    }
                },
                children=blocks
            )
            print(f"[OK] [NotionReporter] Report Created: {new_page['url']}")
            return new_page['url']
        except Exception as e:
            print(f"[ERROR] [NotionReporter] Report Insertion Failed: {e}")
            if hasattr(e, "body"):
                print(f"상세 에러: {e.body}")
            return None

if __name__ == "__main__":
    print("=== NotionReporter 수동 실행 ===")
    reporter = NotionReporter()
    if reporter.client and reporter.parent_page_id:
        url = reporter.create_daily_report()
        if url:
            print(f"생성된 데일리 리포트 URL: {url}")
    else:
        print("설정이 누락되어 실행할 수 없습니다. config.py의 NOTION_PARENT_PAGE_ID를 확인하세요.")
