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
from analysis.pairs_trading import PairsTradingAnalyzer
from analysis.event_swing import EventSwingAnalyzer
from analysis.value_investing import ValueInvestingAnalyzer
from analysis.short_squeeze import ShortSqueezeAnalyzer
from analysis.derivatives import DerivativesAnalyzer

class NotionReporter:
    def __init__(self):
        if not NOTION_API_KEY:
            self.client = None
            print("[WARN] [NotionReporter] NOTION_API_KEY가 설정되지 않아 비활성화됩니다.")
        else:
            self.client = Client(auth=NOTION_API_KEY)
            
        self.db = SupabaseManager()
        self.parent_page_id = NOTION_PARENT_PAGE_ID
        
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
                    "rich_text": [{"type": "text", "text": {"content": "매일 아침 8시(KST) 자동 갱신되는 전문가 수준의 데일리 퀀트 브리핑 아카이브입니다.\n상세한 분석 내용은 생성된 하위 페이지를 클릭하여 확인하세요."}}],
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
                    "rich_text": [{"type": "text", "text": {"content": "📚 데일리 브리핑 페이지 목록"}}]
                }
            }
        ]
        
        self.client.blocks.children.append(
            block_id=self.parent_page_id,
            children=widget_blocks
        )
        
        print(f"[OK] Dashboard Setup Complete!")
        return self.parent_page_id

    def get_or_create_database(self):
        """하위 호환성을 위한 stub 메서드"""
        return self.parent_page_id

    def create_daily_report(self):
        """GAS 이메일 리포트 양식을 본딴 노션 하위 페이지 리포트 생성"""
        if not self.client or not self.parent_page_id:
            return None
            
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # 1. 데이터 로드 (DB + 실시간 분석 모듈 연동)
        recent_assets = self.db.get_recent_high_ev_assets(limit=10)
        macro_dict = self.db.get_latest_macro()
        rag_text = self.db.get_latest_rag_insight()
        
        # 신규 전략 모듈 즉시 수행 (브릿지)
        pairs_analyzer = PairsTradingAnalyzer()
        swing_analyzer = EventSwingAnalyzer()
        value_analyzer = ValueInvestingAnalyzer()
        squeeze_analyzer = ShortSqueezeAnalyzer()
        deriv_analyzer = DerivativesAnalyzer()
        
        # 1. 관심 페어 분석
        pair_results = []
        try:
            pair_results.append(pairs_analyzer.analyze_pair("BTC-USD", "ETH-USD", "1y"))
            pair_results.append(pairs_analyzer.analyze_pair("105560.KS", "055550.KS", "1y"))
        except Exception as e:
            print(f"[WARN] 페어 분석 런타임 오류: {e}")
            
        # 2. 관심 이벤트 분석
        swing_results = []
        try:
            swing_results.append(swing_analyzer.analyze_event_swing_ev("005930.KS", "자사주 매입"))
            swing_results.append(swing_analyzer.analyze_event_swing_ev("086520.KQ", "대규모 유상증자"))
        except Exception as e:
            print(f"[WARN] 스윙 이벤트 분석 런타임 오류: {e}")

        # 3. 밸류에이션 / 숏스퀴즈 / 파생상품 분석 (종합 점검)
        complex_results = []
        try:
            # 가치투자 (삼전, NVDA 샘플)
            complex_results.append({"type": "VALUE", "res": value_analyzer.analyze_intrinsic_value("005930.KS")})
            complex_results.append({"type": "VALUE", "res": value_analyzer.analyze_intrinsic_value("NVDA")})
            # 숏스퀴즈 (TSLA, GME 샘플)
            complex_results.append({"type": "SQUEEZE", "res": squeeze_analyzer.calculate_squeeze_score("TSLA")})
            # 파생상품 (선물 기반 레버리지 리스크 점검)
            complex_results.append({"type": "DERIV", "res": deriv_analyzer.analyze_leverage_risk("TQQQ", leverage=3.0)})
        except Exception as e:
            print(f"[WARN] 복합 분석 런타임 오류: {e}")

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
                    try:
                        ev_val = float(ev_score)
                        ev_str = f"EV. {ev_val:.4f}"
                        ev_color = "green" if ev_val > 0 else "red"
                    except:
                        ev_str = f"EV. {ev_score}"
                        ev_color = "orange"
                        
                    asset_rows.append({
                        "type": "table_row",
                        "table_row": {
                            "cells": [
                                [{"type": "text", "text": {"content": f"💎 추천: {symbol}"}, "annotations": {"bold": True}}],
                                [{"type": "text", "text": {"content": ev_str}, "annotations": {"color": ev_color, "bold": True}}],
                                [{"type": "text", "text": {"content": "종가"}}],
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
        
        # 섹션 1.5: 신규 퀀트 전략(페어 트레이딩 & 이벤트 스윙) 알림판
        blocks.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "⚡ 데일리 퀀트 알파 전략 시그널 (Pair & Swing)"}}]}
        })
        
        quant_strats_rows = []
        # 페어 트레이딩 테이블 행 추가
        for res in pair_results:
            if 'error' in res: continue
            pair_name = res.get('pair', '')
            signal = res.get('signal', 'HOLD')
            current_z = res.get('current_z_score', 0)
            ev = res.get('risk_metrics', {}).get('expected_value_pct', 0)
            reason = res.get('reason', '')
            
            signal_color = "red" if signal == "SHORT_SPREAD" else "blue" if signal == "LONG_SPREAD" else "gray"
            ev_color = "green" if ev > 0 else "red"
            
            quant_strats_rows.append({
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": "🔗 페어 트레이딩"}, "annotations": {"bold": True}}],
                        [{"type": "text", "text": {"content": pair_name}}],
                        [{"type": "text", "text": {"content": f"신호: {signal}"}, "annotations": {"color": signal_color, "bold": True}}],
                        [{"type": "text", "text": {"content": f"Z-Score: {current_z}"}}],
                        [{"type": "text", "text": {"content": f"EV: {ev*100:.2f}%"}, "annotations": {"color": ev_color, "bold": True}}],
                        [{"type": "text", "text": {"content": reason[:20]+".."}, "annotations": {"italic": True}}]
                    ]
                }
            })
            
        # 이벤트 스윙 테이블 행 추가
        for res in swing_results:
            ticker = res.get('ticker', '')
            keyword = res.get('event_keyword', '')
            signal = res.get('signal', 'HOLD')
            ev = res.get('expected_value_pct', 0)
            reason = res.get('reason', '')
            
            signal_color = "red" if signal == "SHORT" else "blue" if signal == "BUY" else "gray"
            ev_color = "green" if ev > 0 else "red"
            
            quant_strats_rows.append({
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": "📰 이벤트 스윙"}, "annotations": {"bold": True}}],
                        [{"type": "text", "text": {"content": f"{ticker} [{keyword}]"}}],
                        [{"type": "text", "text": {"content": f"신호: {signal}"}, "annotations": {"color": signal_color, "bold": True}}],
                        [{"type": "text", "text": {"content": "-"}}],
                        [{"type": "text", "text": {"content": f"EV: {ev*100:.2f}%"}, "annotations": {"color": ev_color, "bold": True}}],
                        [{"type": "text", "text": {"content": reason[:25]+".."}, "annotations": {"italic": True}}]
                    ]
                }
            })
            
        if not quant_strats_rows:
            quant_strats_rows.append({
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": "신규 알파 시그널 없음"}}], [{"type": "text", "text": {"content": "-"}}], [{"type": "text", "text": {"content": "-"}}], [{"type": "text", "text": {"content": "-"}}], [{"type": "text", "text": {"content": "-"}}], [{"type": "text", "text": {"content": "-"}}]
                    ]
                }
            })

        blocks.append({
            "object": "block",
            "type": "table",
            "table": {
                "table_width": 6,
                "has_column_header": False,
                "has_row_header": False,
                "children": quant_strats_rows
            }
        })
        
        # 섹션 1.6: 복합 전략 (Value / Squeeze / Deriv)
        blocks.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "🧩 복합 퀀트 스캔 (Value, Squeeze, Derivatives)"}}]}
        })
        
        complex_rows = []
        for item in complex_results:
            ctype = item['type']
            r = item['res']
            symbol = r.get('symbol') or r.get('ticker') or "-"
            
            if ctype == "VALUE":
                safety = r.get('margin_of_safety', 0)
                ev = r.get('expected_return_pct', 0)
                complex_rows.append({
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": "💎 가치투자"}}],
                            [{"type": "text", "text": {"content": symbol}}],
                            [{"type": "text", "text": {"content": f"안전마진: {safety:.1f}%"}}],
                            [{"type": "text", "text": {"content": f"기대수익: {ev:.1f}%"}, "annotations": {"bold": True, "color": "blue" if ev > 0 else "red"}}],
                            [{"type": "text", "text": {"content": r.get('fair_value_status', '-')}}],
                            [{"type": "text", "text": {"content": "-"}}]
                        ]
                    }
                })
            elif ctype == "SQUEEZE":
                score = r.get('squeeze_potential_score', 0)
                complex_rows.append({
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": "🚀 숏스퀴즈"}}],
                            [{"type": "text", "text": {"content": symbol}}],
                            [{"type": "text", "text": {"content": f"Score: {score}/100"}}],
                            [{"type": "text", "text": {"content": r.get('squeeze_signal', 'HOLD'), "annotations": {"bold": True}}}],
                            [{"type": "text", "text": {"content": f"공매도비율: {r.get('short_interest_ratio', 0):.1f}%"}}],
                            [{"type": "text", "text": {"content": "-"}}]
                        ]
                    }
                })
            elif ctype == "DERIV":
                var = r.get('risk_metrics', {}).get('var_95_pct', 0)
                complex_rows.append({
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": "⛓️ 파생/레버리지"}}],
                            [{"type": "text", "text": {"content": symbol}}],
                            [{"type": "text", "text": {"content": f"VaR(95): {var:.2f}%"}}],
                            [{"type": "text", "text": {"content": f"결정: {r.get('recommendation', 'HOLD')}"}}],
                            [{"type": "text", "text": {"content": f"리스크: {r.get('risk_level', '-')}"}}],
                            [{"type": "text", "text": {"content": "-"}}]
                        ]
                    }
                })
        
        if not complex_rows:
            complex_rows.append({"type": "table_row", "table_row": {"cells": [[{"type": "text", "text": {"content": "복합 분석 결과 없음"}}], [{"type": "text", "text": {"content": "-"}}], [{"type": "text", "text": {"content": "-"}}], [{"type": "text", "text": {"content": "-"}}], [{"type": "text", "text": {"content": "-"}}], [{"type": "text", "text": {"content": "-"}}]]}})

        blocks.append({
            "object": "block",
            "type": "table",
            "table": {
                "table_width": 6,
                "has_column_header": False,
                "has_row_header": False,
                "children": complex_rows
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

                # 핵심 요약 (주황색 콜아웃 혹은 인용구)
                if "[핵심 요약]" in line or "1줄 문장 요약" in line:
                    clean_text = line.replace("[핵심 요약]", "").replace("1줄 문장 요약", "").strip()
                    if clean_text.startswith(":") or clean_text.startswith("-"):
                        clean_text = clean_text[1:].strip()
                        
                    blocks.append({
                        "object": "block",
                        "type": "quote",
                        "quote": {
                            "rich_text": [{"type": "text", "text": {"content": f"🎯 {clean_text}"}, "annotations": {"bold": True, "color": "purple"}}],
                            "color": "purple_background"
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

        # 3. 노션 하위 페이지 생성 API 호출 (데이터베이스 표 대신 자식 페이지로 직접 추가)
        try:
            print(f"[NotionReporter] Inserting report page under parent: {self.parent_page_id}")
            new_page = self.client.pages.create(
                parent={"type": "page_id", "page_id": self.parent_page_id},
                properties={
                    "title": {
                        "title": [{"type": "text", "text": {"content": f"📊 Daily 브리핑 ({today_str}) - {strat_mode}"}}]
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
