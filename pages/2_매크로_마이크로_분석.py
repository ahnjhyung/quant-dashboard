"""
Macro / Micro Analysis Dashboard
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Macro / Micro Analysis | Quant Investment Program", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");
:root {
    --primary: #4f46e5; --success: #059669; --danger: #dc2626;
    --warning: #d97706; --bg: #f8fafc; --card: #ffffff;
    --border: rgba(0,0,0,0.08); --text: #1e293b; --muted: #64748b;
}
* { font-family: 'Pretendard', system-ui, sans-serif; }
[data-testid="stAppViewContainer"] { background: var(--bg); }
[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid var(--border); }

.indicator-block {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px 16px 14px;
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: left;
    margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    position: relative;
    overflow: hidden;
}
.indicator-block:hover {
    border-color: var(--primary);
    box-shadow: 0 4px 12px rgba(79,70,229,0.15);
    transform: translateY(-1px);
}
.indicator-block.selected {
    border-color: var(--primary);
    background: linear-gradient(135deg, #f0f0ff 0%, #ffffff 100%);
}
.block-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 20px;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
}
.badge-daily { background: #dbeafe; color: #1d4ed8; }
.badge-weekly { background: #dcfce7; color: #15803d; }
.badge-monthly { background: #fef3c7; color: #92400e; }
.block-name { font-size: 0.82rem; color: var(--muted); font-weight: 600; margin-bottom: 6px; }
.block-value { font-size: 1.4rem; font-weight: 800; color: var(--text); line-height: 1.1; }
.block-delta { font-size: 0.82rem; font-weight: 600; margin-top: 4px; }
.block-updated { font-size: 0.7rem; color: var(--muted); margin-top: 6px; }

.chart-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    margin-bottom: 16px;
}
.desc-card {
    background: #f0f4ff;
    border-left: 4px solid var(--primary);
    border-radius: 0 8px 8px 0;
    padding: 16px 20px;
    margin-bottom: 16px;
}
.stTabs [data-baseweb="tab-list"] { gap: 24px; }
.stTabs [data-baseweb="tab"] { font-weight: 600; }
</style>
""", unsafe_allow_html=True)

from analysis.value_investing import ValueInvestingAnalyzer
from analysis.swing_trading import SwingTradingAnalyzer
from data_collectors.supabase_manager import SupabaseManager

db = SupabaseManager()

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<h2 style='margin-top:0; color:#1e293b; font-weight:700;'>Quant Investment Program</h2>", unsafe_allow_html=True)
    st.markdown("### 분석 모드")
    mode = st.radio("메뉴", ["매크로 분석", "마이크로 분석"], index=0, label_visibility="collapsed")
    st.markdown("---")
    if mode == "마이크로 분석":
        ticker_input = st.text_input("종목 코드 (Ticker)", value="NVDA", help="예: TSLA, AAPL, 005930.KS")
        period = st.selectbox("분석 범위", ["6개월", "1년", "2년", "5년"], index=1)
        period_map = {"6개월": "6mo", "1년": "1y", "2년": "2y", "5년": "5y"}
        selected_period = period_map[period]
        run_btn = st.button("분석 시작", use_container_width=True, type="primary")
    else:
        ticker_input, run_btn, selected_period = "", False, "1y"
    st.caption("Quant Investment Program v4.5")

# ════════════════════════════════════════════════════════════════
#  MACRO ANALYSIS
# ════════════════════════════════════════════════════════════════
if mode == "매크로 분석":
    st.markdown("<h2 style='color:#1e293b; font-weight:800; margin-bottom:4px;'>Macro / Micro Analysis</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color:#64748b; margin-bottom:32px;'>글로벌 거시경제 지표를 한눈에 확인하고 클릭하여 상세 차트와 해석을 확인합니다.</p>", unsafe_allow_html=True)

    # ── Indicator Definitions ────────────────────────────────────
    INDICATORS = [
        # key, name, unit, freq, color, thresholds, description, category
        {
            "key": "T10Y2Y", "name": "장단기 금리차 (10Y-2Y)", "unit": "%", "freq": "Daily",
            "color": "#4f46e5",
            "thresholds": [{"label": "경기침체 경고", "value": 0, "color": "red"}, {"label": "정상화", "value": 0.5, "color": "green"}],
            "desc": "<b>장단기 금리차</b>는 경기침체의 가장 강력한 선행 지표입니다. 값이 0 아래(역전)로 진입한 뒤 다시 플러스로 돌아올 때 역사적으로 침체가 발생했습니다. 현재 마이너스이면 향후 12~18개월 이내 경기침체 리스크가 존재합니다.",
            "good_low": True,
        },
        {
            "key": "DGS10", "name": "미 10년물 국채금리", "unit": "%", "freq": "Daily",
            "color": "#0ea5e9",
            "thresholds": [{"label": "고금리 경계", "value": 4.5, "color": "red"}, {"label": "중립", "value": 3.5, "color": "orange"}],
            "desc": "<b>10년물 국채금리</b>는 장기 성장 및 인플레이션 기대를 반영하며, 주식 밸류에이션의 할인율로 작용합니다. 금리 상승 시 주식(특히 성장주) 가치 하락 압력이 증가합니다.",
            "good_low": True,
        },
        {
            "key": "DGS2", "name": "미 2년물 국채금리", "unit": "%", "freq": "Daily",
            "color": "#8b5cf6",
            "thresholds": [{"label": "고금리 경계", "value": 4.5, "color": "red"}],
            "desc": "<b>2년물 국채금리</b>는 연준의 단기 정책금리 경로를 가장 민감하게 반영합니다. 연준의 금리 인상/인하 기대가 즉각 반영됩니다.",
            "good_low": True,
        },
        {
            "key": "SOFR", "name": "SOFR 금리", "unit": "%", "freq": "Daily",
            "color": "#06b6d4",
            "thresholds": [{"label": "연준 목표 상단", "value": 5.5, "color": "red"}, {"label": "중립 금리", "value": 2.5, "color": "green"}],
            "desc": "<b>SOFR (Secured Overnight Financing Rate)</b>은 LIBOR를 대체한 달러화 단기 기준금리입니다. 달러 조달 비용의 실시간 지표로, 금융 시스템의 유동성 압박을 파악하는 데 핵심적입니다.",
            "good_low": True,
        },
        {
            "key": "VIXCLS", "name": "VIX 공포지수", "unit": "", "freq": "Daily",
            "color": "#ef4444",
            "thresholds": [{"label": "극도 공포 (매수 기회)", "value": 30, "color": "red"}, {"label": "경계 구간", "value": 20, "color": "orange"}, {"label": "과도한 낙관 (주의)", "value": 15, "color": "blue"}],
            "desc": "<b>VIX</b>는 S&P 500 옵션 가격에서 산출되는 30일 내재 변동성입니다. 30 이상은 극도의 공포 구간으로 역사적 매수 기회, 15 미만은 과도한 낙관으로 조정 가능성을 시사합니다.",
            "good_low": True,
        },
        {
            "key": "DEXKOUS", "name": "원/달러 환율", "unit": "₩", "freq": "Daily",
            "color": "#f59e0b",
            "thresholds": [{"label": "위기 레벨", "value": 1400, "color": "red"}, {"label": "경계 구간", "value": 1300, "color": "orange"}],
            "desc": "<b>원/달러 환율</b>은 외국인 자금 유출입의 핵심 지표입니다. 1,300원 돌파 시 외국인 매도 심화, 1,400원 이상은 외환위기 수준의 압박을 의미합니다.",
            "good_low": True,
        },
        {
            "key": "BAMLH0A0HYM2", "name": "하이일드 스프레드", "unit": "%", "freq": "Daily",
            "color": "#dc2626",
            "thresholds": [{"label": "신용 위기 경보", "value": 7.0, "color": "red"}, {"label": "경계 구간", "value": 4.0, "color": "orange"}, {"label": "정상 구간", "value": 3.0, "color": "green"}],
            "desc": "<b>하이일드 스프레드 (BAMLH0A0HYM2)</b>는 정크본드와 국채 간 금리 차이입니다. 스프레드 확대는 기업 부도 리스크 증가 및 신용 경색을 의미합니다. 4% 이상이면 경계, 7% 이상이면 신용 위기 수준입니다.",
            "good_low": True,
        },
        {
            "key": "NET_LIQUIDITY", "name": "실질 순유동성", "unit": "B", "freq": "Weekly",
            "color": "#10b981",
            "thresholds": [{"label": "유동성 축소 경계", "value": 5500, "color": "orange"}],
            "desc": "<b>실질 순유동성 = 연준 총자산 - TGA - RRP</b>입니다. 실제 시장에 공급된 달러 규모를 측정하며, 주가와 높은 상관관계를 보입니다. 순유동성 증가 = 자산시장 우호, 감소 = 자산시장 압박.",
            "good_low": False,
        },
        {
            "key": "WALCL_B", "name": "연준 총자산 (Fed Assets)", "unit": "B", "freq": "Weekly",
            "color": "#059669",
            "thresholds": [{"label": "QT 임계점", "value": 7000, "color": "orange"}],
            "desc": "<b>연준 총자산</b>은 양적완화(QE)/긴축(QT)의 척도입니다. 자산 증가 = 달러 공급 확대(주식 우호), 자산 감소(QT) = 달러 회수(주식 부담).",
            "good_low": False,
        },
        {
            "key": "RRPONTSYD", "name": "역레포 잔액 (RRP)", "unit": "B", "freq": "Daily",
            "color": "#6366f1",
            "thresholds": [{"label": "유동성 소진 임박", "value": 100, "color": "red"}, {"label": "정상 구간", "value": 500, "color": "green"}],
            "desc": "<b>역레포 잔액 (RRPONTSYD)</b>은 시중에 갈 곳 없는 유휴 달러가 연준에 주차된 규모입니다. 잔액 감소는 유동성이 시장으로 공급되는 신호이며, 0에 근접하면 추가 유동성 공급이 어려워집니다.",
            "good_low": False,
        },
        {
            "key": "TGA_B", "name": "재무부 일반계정 (TGA)", "unit": "B", "freq": "Weekly",
            "color": "#0891b2",
            "thresholds": [{"label": "부채한도 임박 경고", "value": 200, "color": "red"}],
            "desc": "<b>TGA (Treasury General Account)</b>는 미국 정부의 당좌예금입니다. TGA 잔고가 줄어들면 정부 지출이 시장으로 유입되어 유동성이 증가합니다. 부채한도 협상 시 TGA 소진 속도가 빨라집니다.",
            "good_low": False,
        },
        {
            "key": "CPIAUCSL", "name": "미국 CPI (소비자물가)", "unit": "", "freq": "Monthly",
            "color": "#f97316",
            "thresholds": [{"label": "Fed 목표치", "value": 2.0, "color": "green"}, {"label": "경계 구간", "value": 3.0, "color": "orange"}, {"label": "고인플레이션", "value": 5.0, "color": "red"}],
            "desc": "<b>CPI (소비자물가지수)</b>는 연준의 통화정책 방향을 결정하는 핵심 지표입니다. 2% 이상 지속 시 금리 인상 압력, 2% 미만 진입 시 금리 인하 기대가 형성됩니다.",
            "good_low": True,
        },
        {
            "key": "UNRATE", "name": "미국 실업률", "unit": "%", "freq": "Monthly",
            "color": "#84cc16",
            "thresholds": [{"label": "침체 신호", "value": 4.5, "color": "red"}, {"label": "완전고용", "value": 4.0, "color": "green"}],
            "desc": "<b>실업률</b>은 경기의 후행 지표입니다. 실업률이 0.5% 이상 급등하면 'Sahm Rule'에 의해 침체 시작으로 판단합니다. 현재 고용 시장의 건전성을 나타냅니다.",
            "good_low": True,
        },
        {
            "key": "ICSA", "name": "주간 실업수당 청구", "unit": "건", "freq": "Weekly",
            "color": "#a855f7",
            "thresholds": [{"label": "경기 둔화 경보", "value": 300000, "color": "red"}, {"label": "정상 수준", "value": 250000, "color": "green"}],
            "desc": "<b>주간 신규 실업수당 청구건수</b>는 고용시장의 가장 실시간에 가까운 지표입니다. 주간 단위 발표로 추세 변화를 빠르게 포착할 수 있습니다. 30만 건 이상 지속 시 경기 둔화 신호.",
            "good_low": True,
        },
    ]

    freq_color = {"Daily": "badge-daily", "Weekly": "badge-weekly", "Monthly": "badge-monthly"}

    # Load latest data
    with st.spinner("매크로 데이터 로딩 중..."):
        latest = db.get_latest_macro() or {}

    # Session state for selected indicator
    if "selected_macro" not in st.session_state:
        st.session_state.selected_macro = "T10Y2Y"

    # ── Block Grid ───────────────────────────────────────────────
    st.markdown("### 주요 거시경제 지표")

    cols_per_row = 4
    rows = [INDICATORS[i:i+cols_per_row] for i in range(0, len(INDICATORS), cols_per_row)]

    for row in rows:
        cols = st.columns(cols_per_row)
        for ci, ind in enumerate(row):
            d = latest.get(ind["key"], {})
            val = d.get("current", None)
            prev = d.get("prev", val)
            delta = (val - prev) if (val is not None and prev is not None) else None
            updated = d.get("date", "N/A")

            is_sel = st.session_state.selected_macro == ind["key"]

            with cols[ci]:
                # Format value
                if val is None:
                    val_str = "N/A"
                    delta_str = ""
                    delta_color = "#64748b"
                else:
                    if ind["unit"] in ["B", "건"]:
                        val_str = f"{val:,.1f}{ind['unit']}"
                    elif ind["unit"] == "₩":
                        val_str = f"{val:,.1f}{ind['unit']}"
                    else:
                        val_str = f"{val:,.2f}{ind['unit']}"

                    if delta is not None and delta != 0:
                        sign = "+" if delta > 0 else ""
                        delta_str = f"{sign}{delta:,.2f}"
                        if ind["good_low"]:
                            delta_color = "#dc2626" if delta > 0 else "#059669"
                        else:
                            delta_color = "#059669" if delta > 0 else "#dc2626"
                    else:
                        delta_str = "0.00"
                        delta_color = "#64748b"

                badge_cls = freq_color.get(ind["freq"], "badge-daily")
                border_style = f"border-color: #4f46e5; background: linear-gradient(135deg,#f0f0ff,#fff);" if is_sel else ""

                if st.button(
                    f"{ind['name']}\n{val_str}  {delta_str}",
                    key=f"btn_{ind['key']}",
                    use_container_width=True,
                ):
                    st.session_state.selected_macro = ind["key"]
                    st.rerun()

                st.markdown(f"""
                <div class="indicator-block {'selected' if is_sel else ''}" style="{border_style}">
                    <span class="block-badge {badge_cls}">{ind['freq']}</span>
                    <div class="block-name">{ind['name']}</div>
                    <div class="block-value">{val_str}</div>
                    <div class="block-delta" style="color:{delta_color};">{delta_str}</div>
                    <div class="block-updated">Last: {updated}</div>
                </div>
                """, unsafe_allow_html=True)

    # ── Detail Panel ─────────────────────────────────────────────
    st.markdown("---")
    sel = next((x for x in INDICATORS if x["key"] == st.session_state.selected_macro), INDICATORS[0])
    st.markdown(f"### {sel['name']} 상세 분석")

    st.markdown(f"""
    <div class="desc-card">
        <div style='font-size:0.75rem; font-weight:700; color:#4f46e5; margin-bottom:8px;'>
            업데이트 주기: {sel['freq']}
        </div>
        <p style='margin:0; color:#1e293b; line-height:1.7;'>{sel['desc']}</p>
    </div>
    """, unsafe_allow_html=True)

    # Load history
    days_map = {"Daily": 1000, "Weekly": 1500, "Monthly": 2500}
    hist_days = days_map.get(sel["freq"], 1000)

    with st.spinner(f"{sel['name']} 차트 로딩 중..."):
        h = db.get_macro_history(sel["key"], days=hist_days)

    if h is not None and not h.empty:
        h = h.dropna()
        if sel["key"] not in ["NET_LIQUIDITY", "WALCL_B", "TGA_B", "RRP_B", "RRPONTSYD"]:
            h = h[h['value'] > 0]

        if not h.empty:
            current_val = h['value'].iloc[-1]

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=h.index, y=h['value'],
                name=sel['name'],
                mode='lines',
                line=dict(color=sel['color'], width=2),
                fill='tozeroy',
                fillcolor=f"rgba(79,70,229,0.07)",
                connectgaps=True
            ))

            # Thresholds
            for th in sel.get("thresholds", []):
                fig.add_hline(
                    y=th["value"],
                    line_dash="dash",
                    line_color=th["color"],
                    line_width=1.5,
                    annotation_text=f" {th['label']} ({th['value']})",
                    annotation_position="top left",
                    annotation_font_size=11,
                    annotation_font_color=th["color"],
                )

            # Current value line
            fig.add_hline(
                y=current_val,
                line_dash="dot",
                line_color="#1e293b",
                line_width=1,
                annotation_text=f" 현재: {current_val:,.2f}{sel['unit']}",
                annotation_position="top right",
                annotation_font_size=12,
                annotation_font_color="#1e293b",
            )

            fig.update_layout(
                height=400,
                margin=dict(l=50, r=50, t=40, b=50),
                template="plotly_white",
                showlegend=False,
                xaxis=dict(title="날짜", showgrid=True, gridcolor="#f1f5f9"),
                yaxis=dict(title=f"{sel['unit']}", showgrid=True, gridcolor="#f1f5f9"),
                plot_bgcolor="#ffffff",
                paper_bgcolor="#ffffff",
            )
            st.plotly_chart(fig, use_container_width=True)

            # Context metrics
            mc1, mc2, mc3, mc4 = st.columns(4)
            with mc1:
                st.metric("현재값", f"{current_val:,.2f}{sel['unit']}")
            with mc2:
                st.metric("52주 최고", f"{h['value'].tail(365).max():,.2f}{sel['unit']}")
            with mc3:
                st.metric("52주 최저", f"{h['value'].tail(365).min():,.2f}{sel['unit']}")
            with mc4:
                avg = h['value'].tail(365).mean()
                st.metric("52주 평균", f"{avg:,.2f}{sel['unit']}")
    else:
        st.warning(f"{sel['name']} 데이터가 아직 수집되지 않았습니다. 데이터 수집기를 먼저 실행해 주세요.")


# ════════════════════════════════════════════════════════════════
#  MICRO ANALYSIS (기존 종목분석 코드 이식)
# ════════════════════════════════════════════════════════════════
elif mode == "마이크로 분석":
    from analysis.swing_trading import SwingTradingAnalyzer
    value_analyzer = ValueInvestingAnalyzer()
    swing_analyzer = SwingTradingAnalyzer()

    st.markdown("<h2 style='color:#1e293b; font-weight:800;'>Micro Analysis</h2>", unsafe_allow_html=True)

    if not ticker_input:
        st.info("사이드바에서 종목 코드를 입력하고 '분석 시작' 버튼을 클릭해 주세요.")
    else:
        if run_btn:
            raw = ticker_input.strip().upper()
            if raw.isdigit() and len(raw) == 6:
                ticker = f"{raw}.KS"
                with st.spinner(f"코스피 데이터 확인 중: {ticker}..."):
                    test_df = swing_analyzer.get_ohlcv(ticker, period="1mo")
                    if test_df.empty:
                        ticker = f"{raw}.KQ"
                        st.caption(f"코스닥({ticker})으로 전환합니다.")
            else:
                ticker = raw

            with st.spinner(f"분석 중: {ticker}..."):
                try:
                    fscore_data = value_analyzer.piotroski_score(ticker)
                    dcf_data = value_analyzer.dcf_valuation(ticker)
                    full_val = value_analyzer.full_value_analysis(ticker)
                    swing_data = swing_analyzer.full_analysis(ticker, period=selected_period)
                    st.session_state.update({
                        'ticker': ticker, 'fscore_data': fscore_data,
                        'dcf_data': dcf_data, 'full_val': full_val, 'swing_data': swing_data
                    })
                except Exception as e:
                    st.error(f"분석 오류: {e}")

        if 'ticker' in st.session_state:
            st.info(f"분석 결과: {st.session_state['ticker']} — 상세 분석은 '종목 분석' 페이지를 이용하시거나 여기서 기본 결과를 확인하세요.")
            fv = st.session_state.get('full_val', {})
            sw = st.session_state.get('swing_data', {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Piotroski F-Score", f"{fv.get('piotroski_score',0)}/9")
            c2.metric("DCF 상승여력", f"{fv.get('upside_pct',0):.1f}%")
            c3.metric("기대값 (EV)", f"{fv.get('expected_value_pct',0):.1f}%")
            c4.metric("스윙 신호", sw.get('signal', 'N/A'))

st.markdown("---")
st.markdown("<p style='text-align:center;color:#94a3b8;font-size:0.82rem;'>Quant Investment Program v4.5 | EV-Based Systematic Investment</p>", unsafe_allow_html=True)
