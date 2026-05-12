"""Macro / Micro Analysis Dashboard"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(
    page_title="Macro / Micro Analysis | Quant Investment Program",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");
* { font-family: 'Pretendard', system-ui, sans-serif; }
[data-testid="stAppViewContainer"] { background: #f8fafc; }
[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid rgba(0,0,0,0.08); }

/* 지표 카드 */
.ind-card {
    background: #ffffff;
    border: 1.5px solid rgba(0,0,0,0.09);
    border-radius: 14px;
    padding: 16px 14px 12px;
    cursor: pointer;
    transition: all 0.18s ease;
    margin-bottom: 10px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    text-decoration: none;
    display: block;
    color: inherit;
}
.ind-card:hover {
    border-color: #4f46e5;
    box-shadow: 0 4px 14px rgba(79,70,229,0.14);
    transform: translateY(-2px);
}
.ind-card.sel {
    border-color: #4f46e5;
    background: linear-gradient(135deg,#f0f0ff 0%,#ffffff 100%);
    box-shadow: 0 4px 14px rgba(79,70,229,0.18);
}
.badge {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 0.67rem;
    font-weight: 700;
    letter-spacing: 0.4px;
    margin-bottom: 7px;
}
.bd { background:#dbeafe; color:#1d4ed8; }
.bw { background:#dcfce7; color:#15803d; }
.bm { background:#fef3c7; color:#92400e; }
.cn { font-size:0.79rem; color:#64748b; font-weight:600; margin-bottom:5px; }
.cv { font-size:1.35rem; font-weight:800; color:#1e293b; line-height:1.1; }
.cd { font-size:0.8rem; font-weight:700; margin-top:3px; }
.cu { font-size:0.68rem; color:#94a3b8; margin-top:5px; }

.desc-box {
    background:#f0f4ff;
    border-left:4px solid #4f46e5;
    border-radius:0 8px 8px 0;
    padding:14px 18px;
    margin-bottom:14px;
}
.freq-tag { font-size:0.72rem; font-weight:700; color:#4f46e5; margin-bottom:6px; }
</style>
""", unsafe_allow_html=True)

from data_collectors.supabase_manager import SupabaseManager
from analysis.value_investing import ValueInvestingAnalyzer
from analysis.swing_trading import SwingTradingAnalyzer

db = SupabaseManager()

# ── Sidebar ──────────────────────────────────
with st.sidebar:
    st.markdown("<h2 style='margin-top:0;color:#1e293b;font-weight:800;'>Quant Investment Program</h2>", unsafe_allow_html=True)
    mode = st.radio("분석 모드", ["매크로 분석", "마이크로 분석"], index=0)
    st.markdown("---")
    if mode == "마이크로 분석":
        ticker_input = st.text_input("종목 코드", "NVDA", help="예: TSLA, AAPL, 005930.KS")
        period = st.selectbox("분석 범위", ["6개월","1년","2년","5년"], index=1)
        period_map = {"6개월":"6mo","1년":"1y","2년":"2y","5년":"5y"}
        sel_period = period_map[period]
        run_btn = st.button("분석 시작", use_container_width=True, type="primary")
    else:
        ticker_input, run_btn, sel_period = "", False, "1y"
    st.caption("Quant Investment Program v4.5")

# ── Indicator definitions ────────────────────
INDICATORS = [
    {"key":"T10Y2Y","name":"장단기 금리차 (10Y-2Y)","unit":"%","freq":"Daily","color":"#4f46e5",
     "thresholds":[{"label":"경기침체 경고","value":0,"color":"red"},{"label":"정상화","value":0.5,"color":"green"}],
     "desc":"<b>장단기 금리차</b>는 경기침체의 가장 강력한 선행 지표입니다. 값이 0 아래(역전)로 진입한 뒤 다시 플러스로 돌아올 때 역사적으로 침체가 발생했습니다. 현재 마이너스이면 향후 12~18개월 이내 경기침체 리스크가 존재합니다.","good_low":True},
    {"key":"DGS10","name":"미 10년물 국채금리","unit":"%","freq":"Daily","color":"#0ea5e9",
     "thresholds":[{"label":"고금리 경계","value":4.5,"color":"red"},{"label":"중립","value":3.5,"color":"orange"}],
     "desc":"<b>10년물 국채금리</b>는 장기 성장 및 인플레이션 기대를 반영하며, 주식 밸류에이션의 할인율로 작용합니다. 금리 상승 시 주식(특히 성장주) 가치 하락 압력이 증가합니다.","good_low":True},
    {"key":"DGS2","name":"미 2년물 국채금리","unit":"%","freq":"Daily","color":"#8b5cf6",
     "thresholds":[{"label":"고금리 경계","value":4.5,"color":"red"}],
     "desc":"<b>2년물 국채금리</b>는 연준의 단기 정책금리 경로를 가장 민감하게 반영합니다. 연준의 금리 인상/인하 기대가 즉각 반영됩니다.","good_low":True},
    {"key":"DGS30","name":"미 30년물 국채금리","unit":"%","freq":"Daily","color":"#0891b2",
     "thresholds":[{"label":"고금리 경계","value":5.0,"color":"red"},{"label":"중립","value":4.0,"color":"orange"}],
     "desc":"<b>30년물 국채금리</b>는 초장기 인플레이션 기대와 재정적자 우려를 반영합니다. 모기지 금리와 직결되어 부동산 시장에 직접적 영향을 미칩니다.","good_low":True},
    {"key":"SOFR","name":"SOFR 금리","unit":"%","freq":"Daily","color":"#06b6d4",
     "thresholds":[{"label":"연준 목표 상단","value":5.5,"color":"red"},{"label":"중립 금리","value":2.5,"color":"green"}],
     "desc":"<b>SOFR</b>은 LIBOR를 대체한 달러화 단기 기준금리입니다. 달러 조달 비용의 실시간 지표로, 금융 시스템의 유동성 압박을 파악하는 데 핵심적입니다.","good_low":True},
    {"key":"VIXCLS","name":"VIX 공포지수","unit":"","freq":"Daily","color":"#ef4444",
     "thresholds":[{"label":"극도 공포(매수 기회)","value":30,"color":"red"},{"label":"경계","value":20,"color":"orange"},{"label":"과도 낙관(주의)","value":15,"color":"blue"}],
     "desc":"<b>VIX</b>는 S&P500 옵션에서 산출되는 30일 내재 변동성입니다. 30 이상은 극도 공포 구간으로 역사적 매수 기회, 15 미만은 과도한 낙관으로 조정 가능성을 시사합니다.","good_low":True},
    {"key":"DEXKOUS","name":"원/달러 환율","unit":"₩","freq":"Daily","color":"#f59e0b",
     "thresholds":[{"label":"위기 레벨","value":1400,"color":"red"},{"label":"경계","value":1300,"color":"orange"}],
     "desc":"<b>원/달러 환율</b>은 외국인 자금 유출입의 핵심 지표입니다. 1,300원 돌파 시 외국인 매도 심화, 1,400원 이상은 외환위기 수준의 압박을 의미합니다.","good_low":True},
    {"key":"BAMLH0A0HYM2","name":"하이일드 스프레드","unit":"%","freq":"Daily","color":"#dc2626",
     "thresholds":[{"label":"신용 위기","value":7.0,"color":"red"},{"label":"경계","value":4.0,"color":"orange"},{"label":"정상","value":3.0,"color":"green"}],
     "desc":"<b>하이일드 스프레드(BAMLH0A0HYM2)</b>는 정크본드와 국채 간 금리 차이입니다. 스프레드 확대는 기업 부도 리스크 증가 및 신용 경색을 의미합니다. 4% 이상 경계, 7% 이상 위기 수준입니다.","good_low":True},
    {"key":"NET_LIQUIDITY","name":"실질 순유동성","unit":"B","freq":"Weekly","color":"#10b981",
     "thresholds":[{"label":"유동성 축소 경계","value":5500,"color":"orange"}],
     "desc":"<b>실질 순유동성 = 연준 총자산 − TGA − RRP</b>입니다. 실제 시장에 공급된 달러 규모를 측정하며 주가와 높은 상관관계를 보입니다. 순유동성 증가 = 자산시장 우호.","good_low":False},
    {"key":"WALCL_B","name":"연준 총자산 (Fed Assets)","unit":"B","freq":"Weekly","color":"#059669",
     "thresholds":[{"label":"QT 임계점","value":7000,"color":"orange"}],
     "desc":"<b>연준 총자산</b>은 양적완화(QE)/긴축(QT)의 척도입니다. 자산 증가 = 달러 공급 확대(주식 우호), 자산 감소(QT) = 달러 회수(주식 부담).","good_low":False},
    {"key":"RRPONTSYD","name":"역레포 잔액 (RRP)","unit":"B","freq":"Daily","color":"#6366f1",
     "thresholds":[{"label":"유동성 소진 임박","value":100,"color":"red"},{"label":"정상","value":500,"color":"green"}],
     "desc":"<b>역레포 잔액(RRPONTSYD)</b>은 시중에 갈 곳 없는 유휴 달러가 연준에 주차된 규모입니다. 잔액 감소는 유동성이 시장으로 공급되는 신호이며, 0에 근접하면 추가 유동성 공급이 어려워집니다.","good_low":False},
    {"key":"TGA_B","name":"재무부 일반계정 (TGA)","unit":"B","freq":"Weekly","color":"#0891b2",
     "thresholds":[{"label":"부채한도 임박","value":200,"color":"red"}],
     "desc":"<b>TGA(Treasury General Account)</b>는 미국 정부의 당좌예금입니다. TGA 잔고가 줄어들면 정부 지출이 시장으로 유입되어 유동성이 증가합니다.","good_low":False},
    {"key":"CPIAUCSL","name":"미국 CPI (소비자물가 YoY)","unit":"%","freq":"Monthly","color":"#f97316",
     "thresholds":[{"label":"Fed 목표","value":2.0,"color":"green"},{"label":"경계","value":3.0,"color":"orange"},{"label":"고인플레이션","value":5.0,"color":"red"}],
     "desc":"<b>CPI(소비자물가지수 YoY)</b>는 연준 통화정책 방향을 결정하는 핵심 지표입니다. 2% 이상 지속 시 금리 인상 압력, 2% 미만 진입 시 금리 인하 기대가 형성됩니다.","good_low":True},
    {"key":"UNRATE","name":"미국 실업률","unit":"%","freq":"Monthly","color":"#84cc16",
     "thresholds":[{"label":"침체 신호","value":4.5,"color":"red"},{"label":"완전고용","value":4.0,"color":"green"}],
     "desc":"<b>실업률</b>은 경기의 후행 지표입니다. 실업률이 0.5%p 이상 급등하면 'Sahm Rule'에 의해 침체 시작으로 판단합니다.","good_low":True},
    {"key":"ICSA","name":"주간 실업수당 청구","unit":"건","freq":"Weekly","color":"#a855f7",
     "thresholds":[{"label":"경기 둔화 경보","value":300000,"color":"red"},{"label":"정상","value":250000,"color":"green"}],
     "desc":"<b>주간 신규 실업수당 청구건수</b>는 고용시장의 가장 실시간에 가까운 지표입니다. 30만 건 이상 지속 시 경기 둔화 신호입니다.","good_low":True},
]

KEY_LIST = [i["key"] for i in INDICATORS]
FREQ_BADGE = {"Daily":"bd","Weekly":"bw","Monthly":"bm"}

# 음수가 정상인 지표 (> 0 필터 미적용)
ALLOW_NEGATIVE = {"T10Y2Y", "T10Y3M", "NET_LIQUIDITY", "NFCI", "BAMLH0A0HYM2"}
# 단위 변환: 건 → 만 건
UNIT_DIVIDERS = {"ICSA": (10000, "만 건")}

# ════════════════════════════════════════════
#  MACRO MODE
# ════════════════════════════════════════════
if mode == "매크로 분석":
    st.markdown("<h2 style='color:#1e293b;font-weight:800;margin-bottom:4px;'>Macro Analysis</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color:#64748b;margin-bottom:28px;'>카드를 클릭하면 상세 차트와 해석을 볼 수 있습니다.</p>", unsafe_allow_html=True)

    # query_params로 선택 상태 관리
    params = st.query_params
    sel_key = params.get("ind", "T10Y2Y")
    if sel_key not in KEY_LIST:
        sel_key = "T10Y2Y"

    # 데이터 한 번에 로드
    with st.spinner("매크로 데이터 로딩 중..."):
        latest = db.get_latest_macro() or {}

    # ── 블록 그리드 (HTML 카드 only, 버튼 없음) ──
    st.markdown("### 주요 거시경제 지표")
    COLS = 4
    rows = [INDICATORS[i:i+COLS] for i in range(0, len(INDICATORS), COLS)]

    for row in rows:
        cols = st.columns(COLS)
        for ci, ind in enumerate(row):
            d = latest.get(ind["key"], {})
            val = d.get("current")
            prev = d.get("prev", val)
            updated = d.get("date", "N/A")
            is_sel = sel_key == ind["key"]

            # 값 포맷
            if val is None:
                val_str, delta_str, delta_color = "N/A", "", "#94a3b8"
            else:
                u = ind["unit"]
                if u == "₩":
                    val_str = f"{val:,.1f}{u}"
                elif u == "B":
                    val_str = f"{val:,.1f}{u}"
                elif u == "건":
                    val_str = f"{int(val):,}{u}"
                else:
                    val_str = f"{val:,.2f}{u}"

                delta = (val - prev) if prev is not None else 0
                sign = "+" if delta > 0 else ""
                delta_str = f"{sign}{delta:,.2f}" if u not in ["B","건","₩"] else f"{sign}{delta:,.1f}"
                if delta == 0:
                    delta_color = "#94a3b8"
                elif ind["good_low"]:
                    delta_color = "#dc2626" if delta > 0 else "#059669"
                else:
                    delta_color = "#059669" if delta > 0 else "#dc2626"

            badge = FREQ_BADGE.get(ind["freq"], "bd")
            sel_cls = "sel" if is_sel else ""

            with cols[ci]:
                # query_params를 변경하는 링크로 카드 클릭 구현
                card_url = f"?ind={ind['key']}"
                st.markdown(f"""
                <a href="{card_url}" target="_self" style="text-decoration:none;">
                <div class="ind-card {sel_cls}">
                    <span class="badge {badge}">{ind['freq']}</span>
                    <div class="cn">{ind['name']}</div>
                    <div class="cv">{val_str}</div>
                    <div class="cd" style="color:{delta_color};">{delta_str}</div>
                    <div class="cu">업데이트: {updated}</div>
                </div>
                </a>
                """, unsafe_allow_html=True)

    # ── 상세 차트 패널 ──
    st.markdown("---")
    sel_ind = next((x for x in INDICATORS if x["key"] == sel_key), INDICATORS[0])
    st.markdown(f"### {sel_ind['name']} 상세 분석")

    st.markdown(f"""
    <div class="desc-box">
        <div class="freq-tag">업데이트 주기: {sel_ind['freq']}</div>
        <p style='margin:0;color:#1e293b;line-height:1.75;'>{sel_ind['desc']}</p>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner(f"{sel_ind['name']} 차트 로딩 중..."):
        h = db.get_macro_history(sel_key, days=3000)

    if h is not None and not h.empty:
        h = h.sort_index()
        h = h[h['value'].notna()]
        # 음수가 정상인 지표는 > 0 필터 미적용
        if sel_key not in ALLOW_NEGATIVE:
            h = h[h['value'] > 0]

        if not h.empty:
            # 단위 변환 (ICSA: 건 → 만 건)
            div, display_unit = UNIT_DIVIDERS.get(sel_key, (1, sel_ind["unit"]))
            plot_values = h['value'] / div
            current_val = float(plot_values.iloc[-1])
            u = display_unit

            if u in ["B", "₩", "만 건"]:
                cur_label = f"{current_val:,.1f} {u}"
                def fmt(v): return f"{v:,.1f} {u}"
            elif u == "건":
                cur_label = f"{int(current_val):,} {u}"
                def fmt(v): return f"{int(v):,} {u}"
            else:
                cur_label = f"{current_val:,.2f}{u}"
                def fmt(v): return f"{v:,.2f}{u}"

            # 리샘플 (일별 데이터가 많을 때 주간 집계로 가독성 개선)
            freq_rs = sel_ind["freq"]
            if freq_rs == "Daily" and len(plot_values) > 400:
                plot_s = plot_values.resample("W").last().dropna()
            elif freq_rs == "Weekly" and len(plot_values) > 300:
                plot_s = plot_values.resample("W").last().dropna()
            else:
                plot_s = plot_values

            # 임계값도 동일하게 나눔
            thresholds_adj = [
                {**th, "value": th["value"] / div}
                for th in sel_ind.get("thresholds", [])
            ]

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=plot_s.index, y=plot_s.values,
                mode='lines',
                line=dict(color=sel_ind["color"], width=2),
                fill='tozeroy',
                fillcolor='rgba(79,70,229,0.06)',
                connectgaps=True,
                name=sel_ind["name"]
            ))

            for th in thresholds_adj:
                fig.add_hline(
                    y=th["value"],
                    line_dash="dash", line_color=th["color"], line_width=1.5,
                    annotation_text=f"  {th['label']} ({th['value']:.1f} {u})",
                    annotation_position="top left",
                    annotation_font_size=11, annotation_font_color=th["color"],
                )

            fig.add_hline(
                y=current_val, line_dash="dot", line_color="#1e293b", line_width=1,
                annotation_text=f"  현재: {cur_label}",
                annotation_position="top right",
                annotation_font_size=12, annotation_font_color="#1e293b",
            )

            fig.update_layout(
                height=420,
                margin=dict(l=60, r=60, t=40, b=50),
                template="plotly_white",
                showlegend=False,
                xaxis=dict(showgrid=True, gridcolor="#f1f5f9", title="날짜"),
                yaxis=dict(showgrid=True, gridcolor="#f1f5f9", title=u),
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
            )
            st.plotly_chart(fig, use_container_width=True)

            mc1, mc2, mc3, mc4 = st.columns(4)
            y1 = plot_values.tail(365)
            mc1.metric("현재값", cur_label)
            mc2.metric("52주 최고", fmt(y1.max()))
            mc3.metric("52주 최저", fmt(y1.min()))
            mc4.metric("52주 평균", fmt(y1.mean()))
        else:
            st.warning(f"{sel_ind['name']}: 유효한 데이터가 없습니다.")
    else:
        st.warning(f"{sel_ind['name']} 데이터가 DB에 없습니다. 데이터 수집기를 실행해 주세요.")

# ════════════════════════════════════════════
#  MICRO MODE
# ════════════════════════════════════════════
elif mode == "마이크로 분석":
    value_analyzer = ValueInvestingAnalyzer()
    swing_analyzer = SwingTradingAnalyzer()

    st.markdown("<h2 style='color:#1e293b;font-weight:800;'>Micro Analysis</h2>", unsafe_allow_html=True)

    if not ticker_input:
        st.info("사이드바에서 종목 코드를 입력하고 '분석 시작' 버튼을 클릭해 주세요.")
    elif run_btn:
        raw = ticker_input.strip().upper()
        if raw.isdigit() and len(raw) == 6:
            ticker = f"{raw}.KS"
            with st.spinner(f"코스피 확인 중: {ticker}"):
                test_df = swing_analyzer.get_ohlcv(ticker, period="1mo")
                if hasattr(test_df,'empty') and test_df.empty:
                    ticker = f"{raw}.KQ"
        else:
            ticker = raw

        with st.spinner(f"분석 중: {ticker}"):
            try:
                fscore = value_analyzer.piotroski_score(ticker)
                dcf = value_analyzer.dcf_valuation(ticker)
                fv = value_analyzer.full_value_analysis(ticker)
                sw = swing_analyzer.full_analysis(ticker, period=sel_period)
                st.session_state.update({'mi_ticker':ticker,'mi_fv':fv,'mi_sw':sw})
            except Exception as e:
                st.error(f"분석 오류: {e}")

    if 'mi_ticker' in st.session_state:
        fv = st.session_state['mi_fv']
        sw = st.session_state['mi_sw']
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Piotroski F-Score", f"{fv.get('piotroski_score',0)}/9")
        c2.metric("DCF 상승여력", f"{fv.get('upside_pct',0):.1f}%")
        c3.metric("기대값 (EV)", f"{fv.get('expected_value_pct',0):.1f}%")
        c4.metric("스윙 신호", sw.get('signal','N/A'))

st.markdown("---")
st.caption("Quant Investment Program v4.5 | EV-Based Systematic Investment")
