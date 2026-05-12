"""Macro / Micro Analysis Dashboard"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_collectors.supabase_manager import SupabaseManager
from analysis.macro_consensus import MacroConsensusEngine

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
    {"key":"NET_LIQUIDITY","name":"실질 순유동성","unit":"$B","freq":"Weekly","color":"#10b981",
     "thresholds":[{"label":"유동성 축소 경계","value":5_500_000,"color":"orange"}],
     "desc":"<b>실질 순유동성 = 연준 총자산 − TGA − RRP</b>입니다. 실제 시장에 공급된 달러 규모를 측정하며 주가와 높은 상관관계를 보입니다. 순유동성 증가 = 자산시장 우호.","good_low":False},
    {"key":"WALCL","name":"연준 총자산 (Fed Assets)","unit":"$B","freq":"Weekly","color":"#059669",
     "thresholds":[{"label":"QT 임계점","value":7_000_000,"color":"orange"}],
     "desc":"<b>연준 총자산</b>은 양적완화(QE)/긴축(QT)의 척도입니다. 자산 증가 = 달러 공급 확대(주식 우호), 자산 감소(QT) = 달러 회수(주식 부담). 단위: 억달러($B).","good_low":False},
    {"key":"RRPONTSYD","name":"역레포 잔액 (RRP)","unit":"$B","freq":"Daily","color":"#6366f1",
     "thresholds":[{"label":"유동성 소진 임박","value":100,"color":"red"},{"label":"정상","value":500,"color":"green"}],
     "desc":"<b>역레포 잔액(RRPONTSYD)</b>은 시중에 갈 곳 없는 유휴 달러가 연준에 주차된 규모입니다. 잔액 감소는 유동성이 시장으로 공급되는 신호이며, 0에 근접하면 추가 유동성 공급이 어려워집니다.","good_low":False},
    {"key":"WDTGAL","name":"재무부 일반계정 (TGA)","unit":"$B","freq":"Weekly","color":"#0891b2",
     "thresholds":[{"label":"부채한도 임박","value":200_000,"color":"red"}],
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

# 단위 변환 테이블: {ticker: (나누는 값, 표시 단위)}
# WALCL/WDTGAL/NET_LIQUIDITY는 FRED에서 '백만달러' 단위로 저장 → ÷1000 → 10억달러($B)
# ICSA는 '건' 단위 → ÷10000 → '만 건'
UNIT_DIVIDERS = {
    "WALCL":        (1_000, "$B"),   # M$ → B$ (7,100,000M → 7,100 $B ≈ $7.1T)
    "WDTGAL":       (1_000, "$B"),   # M$ → B$ (700,000M  → 700 $B ≈ $0.7T)
    "NET_LIQUIDITY":(1, "$B"),       # 이미 B$ 단위로 저장됨
    "ICSA":         (10_000, "만 건"),
}

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
        
    # --- 매크로 컨센서스 분석 결과 ---
    consensus_engine = MacroConsensusEngine()
    consensus_res = consensus_engine.analyze_macro_consensus()
    score = consensus_res['score']
    c_color = consensus_res['color']
    
    st.markdown(f"""
    <div style="background: white; border-radius: 16px; padding: 24px; margin-bottom: 30px; border: 1px solid rgba(0,0,0,0.08); box-shadow: 0 4px 20px rgba(0,0,0,0.04);">
        <h3 style="margin-top: 0; color: #1e293b; font-weight: 700; margin-bottom: 20px;">매크로 투자 컨센서스 (AI)</h3>
        <div style="display: flex; gap: 24px; align-items: center; flex-wrap: wrap;">
            <div style="flex: 0 0 auto; text-align: center; padding: 20px 30px; background: {c_color}15; border-radius: 12px; border: 1px solid {c_color}30;">
                <div style="font-size: 14px; font-weight: 600; color: {c_color}; margin-bottom: 4px;">Score</div>
                <div style="font-size: 36px; font-weight: 800; color: {c_color}; line-height: 1;">{score}</div>
                <div style="font-size: 12px; color: #64748b; margin-top: 4px;">-100 ~ +100</div>
            </div>
            <div style="flex: 1 1 300px;">
                <div style="font-size: 24px; font-weight: 800; color: {c_color}; margin-bottom: 8px;">{consensus_res['consensus']}</div>
                <div style="font-size: 16px; color: #334155; line-height: 1.5; font-weight: 500;">{consensus_res['action_plan']}</div>
            </div>
            <div style="flex: 1 1 300px; background: #f8fafc; padding: 16px; border-radius: 12px; font-size: 13px; color: #475569; line-height: 1.6;">
                <strong style="color: #1e293b;">주요 판단 근거:</strong><br>
                {'<br>'.join(consensus_res['details'])}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

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
                # 단위 변환 적용 (카드 표시)
                cdiv, cu = UNIT_DIVIDERS.get(ind["key"], (1, ind["unit"]))
                dval  = val  / cdiv
                dprev = prev / cdiv if prev is not None else None

                if cu in ["$B"]:
                    val_str = f"{dval:,.0f} {cu}"
                elif cu == "만 건":
                    val_str = f"{dval:,.1f} {cu}"
                elif cu == "₩":
                    val_str = f"{dval:,.1f}{cu}"
                elif cu == "건":
                    val_str = f"{int(dval):,}{cu}"
                else:
                    val_str = f"{dval:,.2f}{cu}"

                delta = (dval - dprev) if dprev is not None else 0
                sign = "+" if delta > 0 else ""
                if cu in ["$B"]:
                    delta_str = f"{sign}{delta:,.0f}"
                elif cu in ["만 건", "₩"]:
                    delta_str = f"{sign}{delta:,.1f}"
                else:
                    delta_str = f"{sign}{delta:,.2f}"
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

    # FRED 무료 API 데이터 한계 안내
    FRED_LIMITED_HISTORY = {
        "BAMLH0A0HYM2": "2023-05",
    }
    if sel_key in FRED_LIMITED_HISTORY:
        st.info(f"[안내] **데이터 출처 한계**: FRED 무료 API는 이 시리즈의 **{FRED_LIMITED_HISTORY[sel_key]} 이후 데이터**만 제공합니다. 전체 히스토리(1996~)는 Bloomberg/Refinitiv 등 유료 데이터 소스가 필요합니다.")

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

            plot_s = plot_values

            # 임계값도 동일하게 나눔
            thresholds_adj = [
                {**th, "value": th["value"] / div}
                for th in sel_ind.get("thresholds", [])
            ]

            fig = go.Figure()
            
            # 음수가 가능한 지표는 채우기 효과 제거
            fill_type = 'none' if sel_key in ALLOW_NEGATIVE else 'tozeroy'
            
            fig.add_trace(go.Scatter(
                x=plot_s.index, y=plot_s.values,
                mode='lines',
                line=dict(color=sel_ind["color"], width=2),
                fill=fill_type,
                fillcolor='rgba(79,70,229,0.06)' if fill_type == 'tozeroy' else None,
                connectgaps=True, # 끊긴 차트 연결
                name=sel_ind["name"]
            ))

            # ICSA(실업수당 청구)의 경우 변동성이 크므로 Bar + 4주 이동평균선
            if sel_key == "ICSA":
                fig.data = [] # 기존 Scatter 제거
                # 단위를 '만 건'으로 조정 (기본 데이터가 건수이므로 10,000으로 나눔)
                icsa_scaled = plot_s / 10000.0
                fig.add_trace(go.Bar(
                    x=icsa_scaled.index, y=icsa_scaled.values,
                    name="주간 신규 (만 건)",
                    marker_color='rgba(168, 85, 247, 0.3)',
                    hovertemplate="%{x|%Y-%m-%d}: %{y:,.1f}만 건<extra></extra>"
                ))
                sma4 = icsa_scaled.rolling(window=4).mean()
                fig.add_trace(go.Scatter(
                    x=sma4.index, y=sma4.values,
                    mode='lines',
                    line=dict(color="#ef4444", width=3),
                    name="4주 이동평균 (만 건)",
                    connectgaps=True
                ))
            
            # 하이일드 스프레드의 경우 변동성이 크므로 연결 강화
            if sel_key == "BAMLH0A0HYM2":
                fig.update_traces(line=dict(width=3))

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

            # 실제 데이터가 있는 구간만 x축 범위로 설정 (빈 구간 방지)
            x_min = plot_s.index.min()
            x_max = plot_s.index.max()
            fig.update_layout(
                height=420,
                margin=dict(l=60, r=60, t=40, b=50),
                template="plotly_white",
                showlegend=False,
                xaxis=dict(
                    showgrid=True, gridcolor="#f1f5f9", title="날짜",
                    range=[x_min, x_max],   # 실제 데이터 범위만 표시
                ),
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
                import yfinance as yf
                stock_info = yf.Ticker(ticker).info
                fv = value_analyzer.full_value_analysis(ticker)
                sw = swing_analyzer.full_analysis(ticker, period=sel_period)
                st.session_state.update({'mi_ticker':ticker,'mi_fv':fv,'mi_sw':sw, 'mi_info':stock_info})
            except Exception as e:
                st.error(f"분석 오류: {e}")

    if 'mi_ticker' in st.session_state:
        ticker = st.session_state['mi_ticker']
        fv = st.session_state['mi_fv']
        sw = st.session_state['mi_sw']
        info = st.session_state['mi_info']
        
        comp_name = info.get('longName', info.get('shortName', ticker))
        current_price = sw.get('current_price', info.get('currentPrice', 0))
        beta = info.get('beta', 'N/A')
        if isinstance(beta, float):
            beta_str = f"{beta:.2f}"
            risk_level = "고위험 (고변동성)" if beta > 1.2 else "저위험 (안정적)" if beta < 0.8 else "시장평균 (보통)"
        else:
            beta_str = "N/A"
            risk_level = "알 수 없음"

        st.markdown(f"### {comp_name} ({ticker})")
        st.markdown(f"**현재가:** {current_price:,.2f} | **베타(Beta):** {beta_str} ({risk_level})")
        
        # 통합 컨센서스 섹션
        st.markdown("#### 종합 투자 컨센서스")
        val_ev = fv.get('expected_value_pct', 0)
        swing_sig = sw.get('swing_signal', 'HOLD')
        swing_ev = sw.get('risk_management', {}).get('expected_value_pct', 0)
        
        if val_ev > 0 and swing_sig in ['BUY', 'STRONG_BUY'] and swing_ev > 0:
            overall_consensus = "강력 매수 (Strong Buy)"
            cons_color = "#16a34a"
            cons_desc = "기본적 분석(내재가치 저평가)과 기술적 분석(상승 모멘텀) 모두 매수 신호를 나타냅니다. 기대값(EV)이 양수입니다."
        elif (val_ev > 0) ^ (swing_sig in ['BUY', 'STRONG_BUY'] and swing_ev > 0):
            overall_consensus = "관망 / 분할 매수 (Hold / Accumulate)"
            cons_color = "#ca8a04"
            cons_desc = "가치 지표와 기술적 지표 간 혼조세가 있습니다. 단기 변동성에 주의하며 분할 접근이 필요합니다."
        else:
            overall_consensus = "매도 / 관망 (Sell / Watch)"
            cons_color = "#dc2626"
            cons_desc = "고평가 혹은 뚜렷한 하락 추세입니다. 신규 진입을 자제하십시오."
            
        st.markdown(f'''
        <div style="padding:15px; border-radius:8px; border-left: 5px solid {cons_color}; background-color: #f8fafc; margin-bottom:20px;">
            <strong style="color: {cons_color}; font-size: 1.1em;">{overall_consensus}</strong><br>
            <span style="color: #475569; font-size: 0.95em;">{cons_desc}</span>
        </div>
        ''', unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["기본적 분석 (Fundamental)", "기술적 분석 (Technical)"])
        
        with tab1:
            st.markdown("#### 핵심 재무 지표 및 가치 평가")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Piotroski F-Score", f"{fv.get('piotroski_score',0)}/9", fv.get('fscore_category',''))
            c2.metric("DCF 상승여력", f"{fv.get('upside_pct',0):.1f}%")
            c3.metric("가치투자 기댓값(EV)", f"{fv.get('expected_value_pct',0):.1f}%")
            c4.metric("PER / PBR", f"{fv.get('per',0):.1f} / {fv.get('pbr',0):.1f}")
            
            st.markdown("##### DCF 기반 안전마진 산출")
            if fv.get('dcf_valid', False):
                st.success(f"DCF 모델 산출 결과, 적정 가치 대비 현재 가격의 안전 마진은 **{fv.get('margin_of_safety',0)*100:.1f}%** 입니다.")
            else:
                st.warning("DCF 분석을 위한 잉여현금흐름(FCF) 데이터가 부족하여 산출되지 않았습니다.")

        with tab2:
            st.markdown("#### 스윙 트레이딩 및 차트 분석")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("스윙 신호", sw.get('swing_signal','N/A'))
            c2.metric("RSI (14)", f"{sw.get('rsi',{{}}).get('value',0):.1f}")
            macd_val = sw.get('macd',{}).get('histogram',0)
            c3.metric("MACD 히스토그램", f"{macd_val:.3f}")
            bb_pct = sw.get('bollinger',{}).get('pct_b',0)
            c4.metric("볼린저 밴드 %B", f"{bb_pct:.2f}")

            risk = sw.get('risk_management', {})
            st.markdown(f"**진입가:** {risk.get('entry',0):,} | **손절가:** {risk.get('stop_loss',0):,} | **목표가:** {risk.get('target',0):,}")
            st.markdown(f"**단기 트레이딩 기댓값(EV):** {risk.get('expected_value_pct',0)*100:.2f}% | **승률 추정치:** {risk.get('win_probability',0)*100:.1f}%")

            df_chart = sw.get('ohlcv')
            if df_chart is not None and not df_chart.empty:
                st.markdown("##### 캔들스틱 및 이동평균 차트")
                fig = go.Figure()
                fig.add_trace(go.Candlestick(
                    x=df_chart.index,
                    open=df_chart['Open'],
                    high=df_chart['High'],
                    low=df_chart['Low'],
                    close=df_chart['Close'],
                    name='Price'
                ))
                
                # 20일 이동평균선 추가
                ma20 = df_chart['Close'].rolling(window=20).mean()
                fig.add_trace(go.Scatter(x=df_chart.index, y=ma20, mode='lines', line=dict(color='blue', width=1), name='MA 20'))
                
                fig.update_layout(
                    height=500,
                    margin=dict(l=40, r=40, t=30, b=30),
                    template="plotly_white",
                    xaxis_rangeslider_visible=False,
                    yaxis_title="Price"
                )
                st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.caption("Quant Investment Program v4.5 | EV-Based Systematic Investment")
