"""
데일리 이메일 리포터
===================
정해진 시간에 최신 분석 결과(페어 트레이딩, 이벤트 스윙)와
수집된 뉴스를 요약하여 담당자에게 이메일로 발송합니다.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, RECIPIENT_EMAIL
from data_collectors.news_scraper import NewsScraper
from analysis.pairs_trading import PairsTradingAnalyzer
from analysis.event_swing import EventSwingAnalyzer
from analysis.macro_cycles import MacroCycleAnalyzer
from analysis.tech_swing_analyzer import TechnicalSwingAnalyzer

# 알려진 티커 한글명 매핑
from data_collectors.ticker_mapper import TICKER_KR_DISPLAY, name_to_ticker

def kr_name(ticker: str) -> str:
    """티커 → 한글명. 없으면 티커 그대로."""
    return TICKER_KR_DISPLAY.get(ticker, ticker)



class EmailReporter:
    def __init__(self):
        self.host = SMTP_HOST
        self.port = SMTP_PORT
        self.user = SMTP_USER
        self.password = SMTP_PASS
        self.recipient = RECIPIENT_EMAIL

    def generate_report_html(self) -> str:
        """분석 모듈들을 실행하여 HTML 리포트를 생성합니다."""
        # 공용 포맷터 함수
        def _fmt(p: float, cur: str = "KRW") -> str:
            return f"${p:,.2f}" if cur == 'USD' else f"{p:,.0f}원"

        # 1. 뉴스 스크래핑
        scraper = NewsScraper()
        events = scraper.fetch_recent_events()

        # 2. 페어 트레이딩 — 4개 카테고리 × 3쌍 = 12쌍
        pairs_analyzer = PairsTradingAnalyzer()
        pairs_results = []

        # ① 암호화폐 (Crypto)
        crypto_pairs = [
            ("BTC-USD", "ETH-USD"),    # 비트코인 vs 이더리움
            ("BTC-USD", "SOL-USD"),    # 비트코인 vs 솔라나
            ("ETH-USD", "SOL-USD"),    # 이더리움 vs 솔라나
        ]
        # ② 한국 주식 (동일 섹터)
        kr_stock_pairs = [
            ("105560.KS", "055550.KS"),  # KB금융 vs 신한지주
            ("086790.KS", "316140.KS"),  # 하나금융 vs 우리금융
            ("005930.KS", "000660.KS"),  # 삼성전자 vs SK하이닉스
            ("373220.KS", "006400.KS"),  # LG에너지솔루션 vs 삼성SDI
            ("051910.KS", "096770.KS"),  # LG화학 vs SK이노베이션
        ]
        # ③ 미국 ETF & 파생상품 관련 (Long-only 매수 가능)
        us_etf_pairs = [
            ("QQQ",  "SPY"),    # 나스닥100 vs S&P500 (기술 vs 전체)
            ("TQQQ", "QQQ"),    # 나스닥 3배레버리지 vs 나스닥 (decay 포착)
            ("GLD",  "TLT"),    # 금 vs 미국장기채 (인플레·금리 방향)
            ("HYG",  "TLT"),    # 하이일드채권 vs 장기채 (신용 스프레드)
        ]
        # ④ 글로벌 매크로 크로스
        macro_pairs = [
            ("GLD",  "SPY"),    # 금 vs 미국 주식 (위험선호도)
            ("005930.KS", "QQQ"),  # 삼성전자 vs 나스닥100
        ]
        # ⑤ 김치 프리미엄 페어 (한국 vs 해외 가격차)
        # · 금 김치: KRX금ETF(132030.KS, 원화가격) vs GLD(달러가격) → 헤지비율로 원달러 환율차 포속
        # · 비트코인 김치: 국내 BTC(KONBIT 프록시: ~BTC-USD) vs 해외 BTC — 국내거래소 상장 ETF로 대리
        kimchi_pairs = [
            ("132030.KS", "GLD"),   # KRX 금ETF(원화) vs GLD(달러) — 금 김치프리미엄
            ("BTC-USD",   "ETH-USD"),  # 왔닫는 코인 김치 대리: 코인 페어 수렴 활용
            ("QQQ",       "069500.KS"),  # 나스닥100 vs KODEX200 (한미 상대 평가)
        ]

        # ⑥ ETF 추적오차 페어 (동일 기초지수 추종 ETF 간 일시적 이격)
        # ──────────────────────────────────────────────────────────────────
        # [전략 근거] 같은 인덱스를 추종하는 ETF는 NAV 차이가 거의 0에 수렴.
        # 수급·운용 방식 차이로 순간 이격(0.1~0.5%) 발생 → 수렴 확률 매우 높음.
        # 상관계수: 0.995~0.999 (일반 페어의 0.7~0.9보다 훨씬 높음)
        etf_tracking_pairs = [
            # ── S&P500 동일 지수 ETF 트리오 ─────────────────────────────
            ("SPY",  "IVV"),    # iShares vs SPDR (모두 S&P500 추종, 운용사만 다름)
            ("SPY",  "VOO"),    # Vanguard vs SPDR (VOO 운용보수 더 낮아 NAV 미묘한 차이)
            # ── 금 ETF (GLD vs IAU) ─────────────────────────────────────
            ("GLD",  "IAU"),    # 동일 금 현물 기반, 운용보수 차이로 NAV 이격 가능
            # ── 반도체 ETF (SOXX vs SMH) ────────────────────────────────
            ("SOXX", "SMH"),    # 구성종목 유사(NVDA·TSMC 대형 공통), 가중방식 차이
            # ── 나스닥100 한미 ETF (QQQ vs 한국상장 ETF) ────────────────
            ("QQQ",  "379800.KS"),  # 나스닥100 ETF(QQQ) vs KODEX나스닥100 (환율 조정 이격)
            # ── 비트코인 현물 ETF (IBIT vs FBTC) ───────────────────────
            ("IBIT", "FBTC"),   # 동일 BTC 현물 기반, 설정사만 다름 (iShares vs Fidelity)
            # ── 레버리지 ETF vs 기초 (decay 비율 포착) ──────────────────
            ("TQQQ", "QQQ"),    # 나스닥 3배레버리지의 비율 추적 오차 (decay 시기 포착)
            ("SOXL", "SOXX"),   # 반도체 3배레버리지 vs 반도체 1배 (decay 타이밍)
        ]

        all_pairs = [
            ("🇰🇷 한국주식", kr_stock_pairs),
        ]
        # ※ 암호화폐·미국 ETF·글로벌 매크로 페어는 국내 장 전략 집중을 위해 제외


        for category, pair_list in all_pairs:
            for y, x in pair_list:
                try:
                    r = pairs_analyzer.analyze_pair(y, x, "1y")
                    r['_category'] = category
                    pairs_results.append(r)
                except Exception as e:
                    print(f"[WARN] 페어 에러 ({y}/{x}): {e}")

        # 3. 이벤트 스윙
        swing_analyzer = EventSwingAnalyzer()
        swing_results = []
        # — 회사명 기준 중복 제거 (유바이오로직스 3개 도같은 뉴스 → 1개만)
        _seen_companies: set[str] = set()
        unique_events: list[dict] = []
        for _ev in events:
            _cn = _ev.get('company_name', '').strip()
            if _cn and _cn not in _seen_companies:
                _seen_companies.add(_cn)
                unique_events.append(_ev)

        for ev in unique_events[:8]:  # 중복 제거 후 최대 8개
            try:
                res = swing_analyzer.analyze_event_swing_ev(ev['company_name'], ev['keyword'])
                res['title'] = ev['title']
                swing_results.append(res)
            except Exception as e:
                print(f"[WARN] 스윙 에러: {e}")

        # BUY 신호만 이메일에 표시, HOLD/AVOID는 백엔드 로그로만
        # 국내(KS/KQ) 종목만 처리, 이벤트 스윙 결과도 국내만
        swing_results = [r for r in swing_results
                         if r.get('ticker','').endswith('.KS')
                         or r.get('ticker','').endswith('.KQ')]
        buy_pairs   = [r for r in pairs_results if r.get('signal') in ('BUY_X', 'BUY_Y') and 'error' not in r]
        # 기대값(EV) 순으로 내림차순 정렬
        buy_pairs.sort(key=lambda x: x.get('risk_metrics', {}).get('expected_value_pct', 0), reverse=True)
        
        hold_pairs  = [r for r in pairs_results if r.get('signal') in ('HOLD', 'AVOID') and 'error' not in r]
        total_scanned = len([r for r in pairs_results if 'error' not in r])

        # 백엔드 로그: HOLD/AVOID 상태는 콘솔에만
        for r in hold_pairs:
            y_t = r.get('ticker_y', '')
            x_t = r.get('ticker_x', '')
            print(f"[BACKGROUND] {y_t}/{x_t}: {r.get('signal','?')} Z={r.get('current_z_score',0):.2f} EV={r.get('risk_metrics',{}).get('expected_value_pct',0)*100:.2f}%")

        # 4. 매크로 국면 판정 (리포트 헤더용)
        macro_analyzer = MacroCycleAnalyzer()
        macro_res = macro_analyzer.get_current_regime()
        m_state = macro_res.get("cycle_state", "NEUTRAL")
        m_weight = macro_res.get("weight_multiplier", 1.0)
        m_details = " | ".join(macro_res.get("details", []))

        # 5. 고도화된 기술적 분석 (Technical Analysis)
        tech_analyzer = TechnicalSwingAnalyzer()
        # 분석 대상: 주요 US 테크, 비트코인, 국내 대형주
        tech_tickers = ["TQQQ", "SOXX", "NVDA", "TSLA", "BTC-USD", "ETH-USD", "005930.KS", "000660.KS"]
        tech_results = tech_analyzer.run_multi_analysis(tech_tickers)
        # 각 티커별 신호를 EV순 정렬하고, 티커 리스트 자체도 최대 EV 순으로 정렬
        for tr in tech_results:
            tr['signals'].sort(key=lambda s: s.get('ev_pct', 0), reverse=True)
        tech_results.sort(key=lambda x: max([s.get('ev_pct', 0) for s in x['signals']]) if x['signals'] else -999, reverse=True)

        # 6. 정성적 리스크 분석 (Contextual Risk Engine) 연동
        from analysis.contextual_risk import ContextualRiskEngine
        risk_engine = ContextualRiskEngine()
        global_risk = risk_engine.get_global_macro_risk()
        g_mult = global_risk.get('global_multiplier', 1.0)
        g_desc = global_risk.get('summary', '안정적')
        final_weight = round(m_weight * g_mult, 2)

        # 빈 문자열 등 제거
        unique_tickers = set()
        for r in buy_pairs:
            unique_tickers.add(r.get('ticker_y', ''))
            unique_tickers.add(r.get('ticker_x', ''))
        for r in swing_results:
            unique_tickers.add(r.get('ticker', ''))
        for res in tech_results:
            unique_tickers.add(res['ticker'])
            
        unique_tickers = {t for t in unique_tickers if t}
        
        risk_cache = {}
        for t in unique_tickers:
            try:
                risk_cache[t] = risk_engine.analyze_ticker_risk(t)
            except Exception as e:
                print(f"[WARN] 리스크 스캔 에러 ({t}): {e}")
                risk_cache[t] = {}

        today = datetime.now().strftime('%Y-%m-%d')

        # 글로벌 리스크 시각적 뱃지
        if g_mult < 1.0:
            risk_header_box = f"""
                <div style="background:#fef5f5; border:1px dashed #e74c3c; padding:12px; border-radius:6px; margin-top:12px; box-shadow: 0 2px 5px rgba(231,76,60,0.1);">
                    <b style="color:#c0392b; font-size:1.05em;">🚨 시장 위험 감지 (Contextual Risk Alert)</b><br/>
                    <div style="margin-top:6px; color:#555; line-height:1.5;">{g_desc}</div>
                    <div style="margin-top:8px; border-top:1px solid #f5b7b1; padding-top:8px;">
                        <small>글로벌 리스크 페널티 적용 후 <b>최종 시스템 가중치: <span style="font-size:1.15em; font-weight:bold; color:#c0392b;">{final_weight}x</span></b></small>
                    </div>
                </div>"""
        else:
            risk_header_box = f"""
                <div style="background:#f4fbf8; border:1px solid #c8e6d9; padding:10px 15px; border-radius:6px; margin-top:12px;">
                    <b style="color:#27ae60; font-size:1.05em;">✅ 평시 안정 상태 (No Global Risk)</b><br/>
                    <div style="margin-top:4px; color:#555; font-size:0.95em;">{g_desc}</div>
                    <div style="margin-top:6px;">
                        <small>안전 페널티 면제 &mdash; <b>시스템 가중치 100% 적용 가능 (<span style="color:#27ae60;font-weight:bold;">{final_weight}x</span>)</b></small>
                    </div>
                </div>"""

        # ── HTML 생성 ───────────────────────────────────────────────────────
        html = f"""
        <html>
        <head>
            <meta charset="utf-8"/>
            <style>
                body {{ font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; padding: 20px; background-color: #fcfcfc; }}
                h2 {{ color: #1a252f; border-bottom: 3px solid #34495e; padding-bottom: 10px; font-weight: 800; }}
                h3 {{ color: #2980b9; margin-top: 35px; font-size: 1.3em; font-weight: 700; border-left: 4px solid #3498db; padding-left: 10px; }}
                .intro {{ background: white; padding: 20px; border-top: 5px solid #2980b9; margin-bottom: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 0.95em; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.03); border-radius: 8px; overflow: hidden; }}
                th {{ background: #f4f6f7; color: #2c3e50; padding: 12px 10px; text-align: left; border-bottom: 2px solid #bdc3c7; font-weight: bold; }}
                td {{ padding: 12px 10px; border-bottom: 1px solid #ecf0f1; vertical-align: middle; }}
                tr:hover {{ background: #fdfefe; }}
                .positive {{ color: #27ae60; font-weight: 800; }}
                .negative {{ color: #e74c3c; font-weight: 800; }}
                .hold {{ color: #95a5a6; font-style: italic; }}
                .signal-buy  {{ background:#27ae60; color:white; padding:4px 10px; border-radius:4px; font-weight:bold; font-size:0.9em; }}
                .signal-short{{ background:#e74c3c; color:white; padding:4px 10px; border-radius:4px; font-weight:bold; font-size:0.9em; }}
                .signal-hold {{ background:#bdc3c7; color:white; padding:4px 10px; border-radius:4px; font-size:0.9em; }}
                .entry-box {{ background:#eaf4fb; border:1px solid #aed6f1; border-radius:6px; padding:8px 12px; margin-top:6px; font-size:0.88em; line-height:1.6; }}
                .basis-box {{ background:#fdfefe; border-left:3px solid #aaa; padding:6px 10px; margin-top:6px; font-size:0.83em; color:#555; line-height:1.5; }}
                .footer {{ color: #a6acb2; font-size: 0.85em; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px; text-align: center; }}
                .scan-summary {{ background:#f0f3f4; border-radius:6px; padding:12px 16px; margin-top:15px; font-size:0.95em; color: #34495e; font-weight: 500; display: inline-block; }}
                .risk-badge {{ background:#fadbd8; color:#c0392b; font-size:0.8em; padding:3px 8px; border-radius:4px; border:1px solid #e6b0aa; font-weight:bold; margin-top:4px; display:inline-block; }}
                .ticker-pill {{ display:inline-block; background:#34495e; color:#fff; padding:3px 8px; border-radius:12px; font-weight:bold; font-size:0.9em; letter-spacing:0.5px; text-decoration:none; }}
                .ev-badge {{ display:inline-block; padding:4px 10px; border-radius:6px; color:#fff; font-weight:bold; font-size:1.1em; letter-spacing:0.5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .ev-pos {{ background: linear-gradient(135deg, #27ae60, #2ecc71); text-shadow: 1px 1px 1px rgba(0,0,0,0.2); }}
                .ev-neg {{ background: linear-gradient(135deg, #c0392b, #e74c3c); }}
                .ev-mid {{ background: #95a5a6; }}
            </style>
        </head>
        <body>
            <h2>퀀트 알파 전략 추천 (EV &gt; 0) &mdash; {today}</h2>
            <div class="intro">
                <p style="margin-top:0; font-size: 1.05em; color: #2c3e50;">
                    <strong>현재 매크로 국면: <span style="color:#e67e22; font-size:1.1em;">{m_state}</span></strong> (사전 정의 가중치 {m_weight}x)<br/>
                    <span style="color:#7f8c8d; font-size: 0.9em;">{m_details}</span>
                </p>
                {risk_header_box}
                <div style="font-size:0.88em; color:#606f7b; background:#f9fbff; padding:10px 12px; border-radius:6px; border-left:4px solid #dae1e7; margin-top:15px; display:flex; align-items:flex-start;">
                    <span><b>가중치(multiplier)란?</b> 현재 시장의 체계적 위험도를 수치화한 할인율입니다. 각 종목별 알고리즘이 도출한 기대수익(EV)에 이 수치가 곱해져 <b>최종 진입 여부와 베팅 규모(비중)</b>가 결정됩니다.</span>
                </div>
                <p>본 메일은 <b>GitHub Cloud 자동화 서버</b>에서 24시간 감시를 통해 생성되었습니다.<br/>
                <p>본 메일은 <b>GitHub Cloud 자동화 서버</b>에서 24시간 감시를 통해 생성되었습니다.<br/>
                <b>분석 결과 진입 에지가 발견된 종목</b>만 표시되며, 테일 리스크 감지 종목은 EV가 페널티 적용됩니다.</p>
                <div class="scan-summary">
                  페어 스캔: 전체 <b>{total_scanned}쌍</b> 분석 → 매수 추천 <b>{len(buy_pairs)}쌍</b>
                </div>
            </div>
        """
         # ── 페어 트레이딩 섹션 — BUY 신호만 표시 ──────────────────────────
        html += f"""
            <h3>페어 트레이딩 분석 리포트 ({len(buy_pairs)}쌍 / 전체 {total_scanned}쌍 스캔)</h3>
            <p style="color:#555; font-size:0.9em; margin-top:-8px;">
              두 자산의 일시적 이격(|Z-Score|&ge;2)시 <b>저평가 자산 매수</b>.
              HOLD/AVOID 종목은 백엔드 로그에만 기록됩니다.
            </p>
        """
        if not buy_pairs:
            html += "<p style='color:#888; text-align:center; padding:20px;'>오늘 매수 추천 페어 없음 — 모든 종목 HOLD/AVOID (정상 국면)</p>"
        else:
            html += """
            <table>
              <tr>
                <th>카테고리</th>
                <th>페어(Pair)</th>
                <th>공적분</th>
                <th>Z-Score</th>
                <th>정보</th>
                <th>기대수익(최종 EV)</th>
              </tr>"""
            prev_category = None
            for r in buy_pairs:
                category = r.get('_category', '')
                cat_cell = f"<b>{category}</b>" if category != prev_category else ""
                prev_category = category

                y_t = r.get('ticker_y', '')
                x_t = r.get('ticker_x', '')
                y_name = kr_name(y_t)
                x_name = kr_name(x_t)
                
                # Risk Badge 추가
                y_risk = risk_cache.get(y_t, {})
                x_risk = risk_cache.get(x_t, {})
                
                y_badge = f"<br/><span class='risk-badge'>{y_risk.get('comment', '')[:20]}..</span>" if y_risk.get('risk_score', 0) >= 0.5 else ""
                x_badge = f"<br/><span class='risk-badge'>{x_risk.get('comment', '')[:20]}..</span>" if x_risk.get('risk_score', 0) >= 0.5 else ""
                
                pair_disp = (f"<b>{y_name}</b> {y_badge}<br/><span style='color:#bdc3c7;font-size:0.8em;margin:2px 0;display:block;'>vs</span><b>{x_name}</b> {x_badge}"
                             f"<br/><div style='margin-top:6px;'><span class='ticker-pill' style='background:#7f8c8d;font-size:0.75em;'>{y_t} / {x_t}</span></div>")

                z        = r.get('current_z_score', 0)
                pval     = r.get('coint_pvalue', '-')
                is_coint = r.get('is_cointegrated', False)
                sig      = r.get('signal', 'HOLD')
                raw_ev_pct = r.get('risk_metrics', {}).get('expected_value_pct', 0) * 100
                buy_target = r.get('buy_target', '')
                
                # EV에 위험 가중치 적용 (보수적 적용: 둘 중 더 높은 리스크 배수를 사용)
                target_risk = y_risk if buy_target == y_t else x_risk
                risk_mult = target_risk.get('risk_multiplier', 1.0)
                ev_pct = raw_ev_pct * risk_mult
                
                coint_badge = "<span style='color:#27ae60;font-weight:bold'>O</span>" if is_coint else "<span style='color:#e74c3c'>X</span>"
                bt_name = kr_name(buy_target)
                buy_html = f"진입:<b style='color:#2980b9;'>{bt_name}</b><br/><span class='ticker-pill' style='background:#3498db;font-size:0.75em;margin-top:4px;'>{buy_target}</span>"
                if not is_coint:
                    buy_html = "<span class='signal-hold'>공적분 미약 (관망)</span>"
            else:
                buy_html = "<span class='hold'>대기 중</span>"

            # EV 표시
            if sig in ('BUY_X', 'BUY_Y') and ev_pct > 0:
                ev_str = f"<div class='ev-badge ev-pos'>+{ev_pct:.2f}%</div>"
                if risk_mult < 1.0:
                    ev_str += f"<br/><small style='color:#e67e22;display:block;margin-top:4px;'>(Risk Penalty {risk_mult}x)</small>"
            elif sig == 'HOLD':
                ev_str = "<div class='ev-badge ev-mid' style='font-size:0.9em;'>진입 미달</div>"
            else:
                ev_str = f"<div class='ev-badge ev-neg'>{ev_pct:.2f}%</div>"

            sig_map = {'BUY_X': 'signal-hold', 'BUY_Y': 'signal-hold',
                       'HOLD': 'signal-hold', 'AVOID': 'signal-hold'}
            sig_cls = sig_map.get(sig, 'signal-hold')

            html += f"""
              <tr>
                <td style='font-size:0.85em'>{cat_cell}</td>
                <td>{pair_disp}</td>
                <td style='text-align:center'>{coint_badge}<br/><small>p={pval}</small></td>
                <td><b>{z:.2f}σ</b></td>
                <td>{buy_html}</td>
                <td>{ev_str}</td>
                <td><span class='{sig_cls}'>{sig}</span></td>
              </tr>"""

        html += "</table>"

        # ── 이벤트 스윙 섹션 (카드형, BUY 전용) ──────────────────────
        buy_swings = [
            r for r in swing_results
            if 'error' not in r and r.get('signal') == 'BUY'  # SHORT/HOLD 완전 제외
        ]
        
        # Risk Multiplier 사전 적용
        for r in buy_swings:
            ticker = r.get('ticker', '')
            r['_risk'] = risk_cache.get(ticker, {})
            rm = r['_risk'].get('risk_multiplier', 1.0)
            r['_final_ev'] = (r.get('expected_value_pct', 0) * 100) * rm
            
        # 기대값(EV) 순으로 내림차순 정렬
        buy_swings.sort(key=lambda x: x.get('_final_ev', 0), reverse=True)

        html += f"""
            <h3>이벤트 스윙 매수 후보 ({len(buy_swings)}종목)</h3>
            <p style="color:#555; font-size:0.9em; margin-top:-8px;">
              과거 유사 이벤트 통계 + 매크로 국면 가중치 + 기술적 분석 결합 →
              <b>최종 EV &gt; +1%인 롱 전략만</b> 표시됩니다. (리스크 페널티 반영됨)
            </p>
        """

        if not buy_swings:
            html += "<p style='color:#888; text-align:center; padding:20px;'>오늘 BUY 신호 종목 없음 (EV 기준 미달)</p>"
        else:
            for r in buy_swings:
                ticker  = r.get('ticker', '')
                kw      = r.get('event_keyword', '')
                regime  = r.get('macro_regime', {}).get('cycle_state', 'Unknown')
                ev_pct  = r.get('_final_ev', 0)
                ev_cls  = 'positive' if ev_pct > 0 else 'negative'
                hist    = r.get('historical_stats', {})
                n_events = hist.get('total_events', '-')
                n_win    = hist.get('win_count', '-')
                win_prob = r.get('adj_win_prob', 0) * 100
                
                rsk = r.get('_risk', {})
                rm = rsk.get('risk_multiplier', 1.0)
                risk_alert = f"<div class='risk-badge'><b>정성적 리스크 감지:</b> {rsk.get('comment', '')} (승수: {rm}x)</div>" if rm < 1.0 else ""

                cur_p   = r.get('current_price', 0)
                ent_p   = r.get('entry_price', 0)
                tgt_p   = r.get('target_price', 0)
                stp_p   = r.get('stop_loss', 0)
                currency = r.get('price_currency', 'KRW')
                price_label = r.get('price_label', '현재가')

                code = ticker.split('.')[0]
                naver_url = f"https://finance.naver.com/item/main.nhn?code={code}"

                # 전략 근거 — | 구분자 → 줄바꿈 처리
                basis = r.get('strategy_basis', '')
                basis_rows = ""
                if basis:
                    for part in basis.split(' | '):
                        part = part.strip()
                        if not part:
                            continue
                        # [근거N] 앞에 아이콘 추가
                        if part.startswith('[근거'):
                            clean_part = part.split(']', 1)[-1].strip() if ']' in part else part
                            basis_rows += f"<tr><td style='padding:4px 0; color:#555; font-size:0.9em'><span style='color:#27ae60;margin-right:4px;'>•</span> {clean_part}</td></tr>"
                        elif part.startswith('[전략]'):
                            clean_part = part.split(']', 1)[-1].strip() if ']' in part else part
                            basis_rows += f"<tr><td style='padding:6px 0; color:#2c3e50; font-size:0.95em'><b>{clean_part}</b></td></tr>"
                        else:
                            basis_rows += f"<tr><td style='padding:4px 0; color:#666; font-size:0.9em'><span style='color:#3498db;margin-right:4px;'>-</span> {part}</td></tr>"

                # 가격 정보 행
                if cur_p > 0:
                    price_info = f"""
                    <tr style='background:#eaf4fb'>
                      <td style='padding:4px 8px'><b>{price_label}</b></td>
                      <td style='padding:4px 8px'><b style='font-size:1.1em'>{_fmt(cur_p)}</b> ({currency})</td>
                    </tr>
                    <tr>
                      <td style='padding:4px 8px; color:#27ae60'><b>▲ 목표가</b></td>
                      <td style='padding:4px 8px; color:#27ae60'><b>{_fmt(tgt_p)}</b>
                          &nbsp;<span style='background:#d5f5e3;padding:2px 6px;border-radius:3px'>+{abs(hist.get('avg_profit',0))*100:.1f}%</span></td>
                    </tr>
                    <tr>
                      <td style='padding:4px 8px; color:#c0392b'><b>▼ 손절가</b></td>
                      <td style='padding:4px 8px; color:#c0392b'><b>{_fmt(stp_p)}</b>
                          &nbsp;<span style='background:#fadbd8;padding:2px 6px;border-radius:3px'>-{abs(hist.get('avg_loss',0))*100:.1f}%</span></td>
                    </tr>"""
                else:
                    price_info = f"""
                    <tr style='background:#fef9e7'>
                      <td colspan='2' style='padding:4px 8px'>
                        현재가 조회 불가 &nbsp;
                        <a href='{naver_url}' target='_blank' style='color:#0366d6'>네이버증권 확인</a>
                      </td>
                    </tr>"""

                html += f"""
                <div style='border:1px solid #d5d8dc; border-radius:8px; margin-bottom:20px; overflow:hidden; font-family:Malgun Gothic,sans-serif'>

                  <!-- 헤더 -->
                  <div style='background:#2c3e50; color:white; padding:12px 16px; display:flex; justify-content:space-between; align-items:center'>
                    <span style='font-size:1.15em; font-weight:bold; display:flex; align-items:center; gap:8px;'>
                      <a href='{naver_url}' target='_blank' style='color:white;text-decoration:none'>{kr_name(ticker)}</a>
                      <span class='ticker-pill'>{ticker}</span>
                      <small style='font-weight:normal;opacity:0.85;margin-left:5px;'>({kw})</small>
                    </span>
                    <span>
                       <div class='ev-badge {ev_cls}'>
                        최종 EV {ev_pct:+.2f}%
                      </div>
                    </span>
                  </div>

                  <div style='display:flex; flex-wrap:wrap'>

                    <!-- 왼쪽: 가격 정보 -->
                    <div style='flex:1; min-width:220px; padding:12px; border-right:1px solid #eee'>
                      {risk_alert}
                      <div style='font-size:0.8em; color:#888; margin-bottom:6px; margin-top:10px; text-transform:uppercase; letter-spacing:.5px'>진입 정보</div>
                      <table style='width:100%; border-collapse:collapse'>
                        {price_info}
                        <tr>
                          <td style='padding:4px 8px; color:#555'>보유기간</td>
                          <td style='padding:4px 8px'>T+1 ~ T+3일 스윙</td>
                        </tr>
                        <tr>
                          <td style='padding:4px 8px; color:#555'>조정 승률</td>
                          <td style='padding:4px 8px'><b>{win_prob:.1f}%</b></td>
                        </tr>
                        <tr>
                          <td style='padding:4px 8px; color:#555'>매크로 국면</td>
                          <td style='padding:4px 8px'>{regime}</td>
                        </tr>
                      </table>
                    </div>

                    <!-- 오른쪽: 투자 근거 -->
                    <div style='flex:2; min-width:280px; padding:12px; background:#fdfefe'>
                      <div style='font-size:0.8em; color:#888; margin-bottom:6px; text-transform:uppercase; letter-spacing:.5px'>투자 근거</div>
                      <table style='width:100%; border-collapse:collapse'>
                        {basis_rows}
                        <tr>
                          <td style='padding:3px 0; color:#888; font-size:0.82em'>
                            과거 {n_events}건 유사이벤트 중 {n_win}건 상승 (기본 승률 {int(n_win)/max(int(n_events),1)*100:.0f}% 추정)
                          </td>
                        </tr>
                      </table>
                    </div>

                  </div>
                </div>"""

        # ── 🔍 고도화된 기술적 분석 섹션 (신규 추가) ──────────────────────
        html += f"""
            <h3>고도화된 기술적 분석 신호 (스윙 & 데이)</h3>
            <p style="color:#555; font-size:0.9em; margin-top:-8px;">
              멀비 지표(BB, RSI, MACD) 결합 + ATR 기반 손익비 설정 → 
              <b>데이트레이딩(1H) 및 스윙(1D) 신호</b>를 추출합니다.
            </p>
        """

        if not tech_results:
            html += "<p style='color:#888; text-align:center; padding:20px;'>현재 기술적 분석상 특이 신호 없음 (관망 국면)</p>"
        else:
            html += """
            <table>
              <tr>
                <th>티커</th>
                <th>주기</th>
                <th>현재가</th>
                <th>전략 및 근거</th>
                <th>기대수익(최종 EV)</th>
                <th>목표/손절</th>
              </tr>"""
            for res in tech_results:
                ticker = res['ticker']
                interval = res['interval']
                price = res['price']
                int_label = "스윙(1D)" if interval == "1d" else "데이(1H)"
                
                rsk = risk_cache.get(ticker, {})
                rm = rsk.get('risk_multiplier', 1.0)
                risk_badge = f"<br/><span class='risk-badge'>{rsk.get('comment', '')[:15]}..</span>" if rm < 1.0 else ""
                
                for sig in res['signals']:
                    raw_ev_pct = sig['ev_pct']
                    ev_pct = raw_ev_pct * rm
                    ev_cls = 'positive' if ev_pct > 0 else 'negative'
                    
                    html += f"""
                    <tr>
                      <td><b>{kr_name(ticker)}</b><br/><span class='ticker-pill' style='margin-top:4px;'>{ticker}</span>{risk_badge}</td>
                      <td style='text-align:center'><span style='background:#e8f4f8;color:#2980b9;padding:4px 8px;border-radius:4px;font-size:0.85em;font-weight:bold;'>{int_label}</span></td>
                      <td><b>{price:,.2f}</b></td>
                      <td>
                        <div style='color:#2c3e50; font-weight:bold; font-size:1.05em; margin-bottom:4px;'>{sig['strategy']}</div>
                        <div style='color:#666; font-size:0.9em; border-left:3px solid #bdc3c7; padding-left:8px;'>{sig['reason']}</div>
                      </td>
                      <td>
                        <div class='ev-badge {"ev-pos" if ev_cls=="positive" else "ev-neg"}'>{ev_pct:+.2f}%</div><br/>
                        <small style="color:#aaa;display:block;margin-top:4px;">(원: {raw_ev_pct:+.2f}%)</small>
                      </td>
                      <td style='font-size:0.9em; background:#fcfcfc; border-left:1px solid #eee;'>
                        <div style='color:#27ae60;margin-bottom:4px;'><b>익절:</b> {_fmt(sig['tp_price'], 'USD' if '-' in ticker or ticker[0].isalpha() else 'KRW')}</div>
                        <div style='color:#e74c3c;'><b>손절:</b> {_fmt(sig['sl_price'], 'USD' if '-' in ticker or ticker[0].isalpha() else 'KRW')}</div>
                      </td>
                    </tr>"""
            html += "</table>"

        html += f"""
            </table>

            <h3>AI 전문가 분석 코멘트 (Contextual Insight)</h3>
            <div style="background:#fdf2e9; border:1px solid #e67e22; border-radius:8px; padding:15px; margin-bottom:20px;">
                <p style="margin:0; font-size:0.95em; color:#d35400;">
                    <strong>[시장 국면 요약]</strong> 현재 시스템 상 매크로 국면은 <b>{m_state}</b>(으)로, 기본 가중치 {m_weight}x를 시사합니다. 하지만 다음과 같은 정량 불가능한 글로벌 리스크가 탐지되었습니다:
                </p>
                <div style="background:#fff; border:1px solid #fad7a1; margin-top:10px; padding:10px; border-radius:6px; color:#c0392b;">
                    <strong>Risk: {g_desc}</strong>
                </div>
                <p style="margin-top:10px; font-size:0.9em; color:#555;">
                    이에 따라, 글로벌 리스크 배수 {g_mult}x를 적용한 최종 시스템 포지션 사이징 한도는 <b>{final_weight}배</b>로 안전을 최우선하는 방향으로 보정되었습니다. 개별 리스크 뱃지가 붙은 종목은 매매 시 각별히 유의하십시오.
                </p>
            </div>
            
            <p class='footer'>
              ※ 본 리포트는 통계적 모델과 과거 데이터에 근거하며 실제 결과와 다를 수 있습니다.<br/>
              EV = (조정승률 × 평균수익) + (패율 × 평균손실) &gt; 0 인 경우만 진입 대상. 최종 투자 책임은 본인에게 있습니다.<br/>
              생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}
            </p>
        </body>
        </html>
        """
        return html

    def send_email(self):
        if not self.user or not self.password or not self.recipient:
            print("[EmailReporter] 이메일 설정 누락 (SMTP_USER, SMTP_PASS, RECIPIENT_EMAIL)")
            return

        try:
            html_content = self.generate_report_html()

            msg = MIMEMultipart("alternative")
            msg['Subject'] = f"[퀀트봇] 오늘의 시장 알파 종목 브리핑 ({datetime.now().strftime('%Y-%m-%d')})"
            msg['From'] = self.user
            msg['To'] = self.recipient

            part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(part)

            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_USER, self.recipient, msg.as_string())

            try:
                print(f"[OK] Email sent to -> {self.recipient}")
            except UnicodeEncodeError:
                print(f"[OK] Email sent.")
        except Exception as e:
            try:
                print(f"[FAILED] Email error: {e}")
            except UnicodeEncodeError:
                print(f"[FAILED] Email error (encoding issue)")


if __name__ == "__main__":
    reporter = EmailReporter()
    print("=== 이메일 리포팅 테스트 ===")
    reporter.send_email()
