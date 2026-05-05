import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from analysis.macro_portfolio_engine import MacroPortfolioEngine
from analysis.macro_optimizer import MacroOptimizer
from data_collectors.macro_backfiller import MacroBackfiller
from datetime import datetime
import numpy as np
import yfinance as yf

# Page Config
st.set_page_config(page_title="포트폴리오 분석 | 통합 퀀트 시스템", layout="wide")

# Notion Embed Detection
is_embed = st.query_params.get("embed", "false").lower() == "true"

# ── Styling: Clean White Theme ───────────────────────────────────────
st.markdown("""
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [data-testid="stAppViewContainer"],
[data-testid="stHeader"], .main {
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', 'Segoe UI', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif !important;
    background-color: #ffffff !important;
    color: #111111;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background-color: #fafafa;
    border-right: 1px solid #e5e5e5;
}
[data-testid="stSidebar"] * {
    color: #333333 !important;
}
[data-testid="stSidebar"] .stMarkdown h3 {
    color: #111111 !important;
    font-weight: 600;
}

/* Stat cards */
.stat-card {
    background: #f8f9fa;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    padding: 16px 18px;
    margin-bottom: 8px;
}
.stat-card .label {
    font-size: 0.75em;
    color: #666666;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-bottom: 6px;
}
.stat-card .value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.5em;
    font-weight: 600;
    color: #111111;
    margin-bottom: 4px;
}
.stat-card .sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8em;
    color: #888888;
}
.stat-card .sub .negative { color: #d32f2f; }
.stat-card .sub .positive { color: #2e7d32; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 1px solid #e0e0e0;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 0;
    padding: 10px 24px;
    background: transparent;
    border: none;
    color: #999999;
    font-weight: 500;
    font-size: 0.88em;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: transparent;
    color: #111111;
    border-bottom: 2px solid #111111;
}

/* Ticker search results */
.ticker-result {
    background: #f5f5f5;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 6px 12px;
    margin: 2px 0;
    font-size: 0.84em;
    color: #333333;
}
.ticker-result .symbol {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    color: #111111;
}
.ticker-result .name { color: #888888; }

/* Expander */
[data-testid="stExpander"] {
    border: 1px solid #e0e0e0;
    border-radius: 6px;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
}

/* Info box */
.info-box {
    background: #f0f4ff;
    border: 1px solid #d0d8f0;
    border-radius: 6px;
    padding: 14px 18px;
    font-size: 0.85em;
    color: #333;
    line-height: 1.6;
    margin: 8px 0;
}

""" + ("""
[data-testid="stSidebar"] { display: none; }
section[data-testid="stSidebarNav"] { display: none; }
""" if is_embed else "") + """
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────
if not is_embed:
    st.markdown("## 포트폴리오 분석 및 비교")
    st.caption("멀티에셋 포트폴리오 백테스팅 및 리스크 최적화 시스템")


# ── Ticker Search Helper ─────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def search_tickers(query: str) -> list:
    """
    yfinance Search API를 사용하여 티커를 검색합니다.
    전 세계 상장 종목을 검색할 수 있습니다.
    """
    if not query or len(query) < 1:
        return []
    try:
        search = yf.Search(query, max_results=15)
        results = []
        for q in search.quotes:
            symbol = q.get("symbol", "")
            name = q.get("shortname") or q.get("longname", "")
            exchange = q.get("exchange", "")
            qtype = q.get("quoteType", "")
            if symbol and qtype in ("EQUITY", "ETF", "CRYPTOCURRENCY", "MUTUALFUND", "INDEX"):
                results.append({
                    "symbol": symbol,
                    "name": name,
                    "exchange": exchange,
                    "type": qtype
                })
        return results
    except Exception:
        return []


# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 설정")
    st.markdown("##### 시작일")
    _col_y, _col_m = st.columns(2)
    with _col_y:
        start_year = st.selectbox(
            "연도", list(range(2025, 1969, -1)),
            index=list(range(2025, 1969, -1)).index(2010),
            key="start_year",
            label_visibility="collapsed"
        )
    with _col_m:
        month_labels = [f"{m}월" for m in range(1, 13)]
        start_month = st.selectbox(
            "월", month_labels,
            index=0,
            key="start_month",
            label_visibility="collapsed"
        )
    start_date = datetime(start_year, month_labels.index(start_month) + 1, 1)

    rebalance_freq = st.selectbox(
        "리밸런싱 주기",
        ["월별 (Monthly)", "분기별 (Quarterly)", "연별 (Yearly)"],
        index=0
    )
    st.caption("선택한 리밸런싱 주기는 모든 포트폴리오에 동일하게 적용됩니다.")
    freq_map = {"월별 (Monthly)": "ME", "분기별 (Quarterly)": "QE", "연별 (Yearly)": "YE"}

    st.markdown("---")

    # Preset Selection
    DEFAULT_PRESETS = {
        "Classic 60/40": {"SPY": 0.6, "TLT": 0.4},
        "All Weather": {"SPY": 0.30, "TLT": 0.40, "IEF": 0.15, "GLD": 0.075, "GSG": 0.075},
        "Permanent": {"SPY": 0.25, "TLT": 0.25, "GLD": 0.25, "SHY": 0.25},
        "Golden Butterfly": {"SPY": 0.2, "IWM": 0.2, "TLT": 0.2, "IEF": 0.2, "GLD": 0.2},
        "S&P 500 Only": {"SPY": 1.0}
    }

    if "custom_presets" not in st.session_state:
        st.session_state.custom_presets = {}

    if "selected_presets" not in st.session_state:
        st.session_state.selected_presets = ["Classic 60/40", "All Weather", "S&P 500 Only"]

    # Apply pending custom preset addition BEFORE the widget is created
    if "_pending_preset" in st.session_state:
        pending_name = st.session_state.pop("_pending_preset")
        current = list(st.session_state.selected_presets)
        if pending_name not in current:
            current.append(pending_name)
        st.session_state.selected_presets = current

    PRESETS = {**DEFAULT_PRESETS, **st.session_state.custom_presets}

    selected_presets = st.multiselect(
        "전략 프리셋 선택",
        list(PRESETS.keys()),
        key="selected_presets"
    )

    with st.expander("전략 설명 보기"):
        st.markdown("""
        - **Classic 60/40**: 
          주식(SPY) 60%와 장기채(TLT) 40%로 구성된 가장 전통적이고 대중적인 자산배분 전략입니다. 포트폴리오의 교과서적인 기준으로 활용됩니다.
        - **Permanent (영구 포트폴리오)**: 
          주식(SPY), 장기채(TLT), 현금(SHY), 금(GLD)에 각각 **25%씩** 배분하는 전략입니다. 경제의 4계절(호황/불황/인플레/디플레)을 모두 방어하기 위해 설계된 초저변동성 전략입니다.
        - **Golden Butterfly**: 
          영구 포트폴리오를 기반으로 수익성을 강화한 전략입니다. 대형주(SPY) 20%, 소형주(IWM) 20%, 장기채(TLT) 20%, 단기채(IEF) 20%, 금(GLD) 20%로 구성됩니다.
        - **All Weather (사계절 포트폴리오)**: 
          레이 달리오가 고안한 전략으로 주식 30%, 중기채 15%, 장기채 40%, 금 7.5%, 원자재 7.5%로 구성됩니다. 각 자산의 리스크(변동성) 비중을 균등하게 맞추어 어떤 경제 상황에서도 안정적인 우상향을 목표로 합니다.
        """)

    st.markdown("---")
    st.caption(f"AGA Quant System v4.5 Premium Edition | {datetime.now().strftime('%Y-%m-%d')}")


# ── Ticker Search & Custom Portfolio Builder ─────────────────────────
with st.expander("Custom Portfolio", expanded=not selected_presets):
    col_search, col_build = st.columns([1, 1])

    with col_search:
        st.markdown("#### 티커 검색")
        st.caption("전 세계 상장 주식, ETF, 암호화폐를 이름 또는 심볼로 검색")
        query = st.text_input(
            "검색",
            placeholder="예: Apple, TSLA, Bitcoin, 삼성전자...",
            label_visibility="collapsed"
        )
        if query:
            with st.spinner("검색 중..."):
                results = search_tickers(query)
            if results:
                for r in results:
                    type_label = {"EQUITY": "주식", "ETF": "ETF", "CRYPTOCURRENCY": "암호화폐",
                                  "MUTUALFUND": "펀드", "INDEX": "지수"}.get(r["type"], r["type"])
                    st.markdown(
                        f'<div class="ticker-result">'
                        f'<span class="symbol">{r["symbol"]}</span> '
                        f'<span class="name">  {r["name"]}</span> '
                        f'<span class="name" style="float:right;">{r["exchange"]} / {type_label}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                st.caption(f"{len(results)}건 검색됨. 심볼을 복사해서 전략 구성에 입력하세요.")
            else:
                st.caption("검색 결과가 없습니다.")

    with col_build:
        st.markdown("#### 직접 전략 구성")
        c_name = st.text_input("전략 이름", "나의 전략")
        c_assets = st.text_input(
            "티커 (쉼표로 구분)",
            "SPY, TLT, GLD",
            help="검색한 티커 심볼을 입력하세요"
        )
        c_weights = st.text_input(
            "비중 % (쉼표로 구분)",
            "50, 30, 20"
        )

        if st.button("포트폴리오 추가"):
            try:
                tickers = [t.strip().upper() for t in c_assets.split(",") if t.strip()]
                weights = [float(w.strip()) / 100.0 for w in c_weights.split(",") if w.strip()]
                if len(tickers) != len(weights):
                    st.error("티커 수와 비중 수가 일치해야 합니다.")
                elif len(tickers) == 0:
                    st.error("최소 1개 이상의 티커를 입력하세요.")
                else:
                    total_w = sum(weights)
                    if abs(total_w - 1.0) > 0.01:
                        weights = [w / total_w for w in weights]
                        st.info(f"비중이 100%로 정규화되었습니다 (기존 {total_w*100:.1f}%)")
                    st.session_state.custom_presets[c_name] = dict(zip(tickers, weights))
                    st.session_state._pending_preset = c_name
                    st.rerun()
            except ValueError:
                st.error("잘못된 비중값입니다. 숫자만 입력하세요.")
            except Exception as e:
                st.error(f"오류: {e}")


# ── Chart Colors (muted, professional) ───────────────────────────────
CHART_COLORS = [
    "#1f77b4",  # blue
    "#ff7f0e",  # orange
    "#2ca02c",  # green
    "#d62728",  # red
    "#9467bd",  # purple
    "#8c564b",  # brown
    "#17becf",  # teal
    "#7f7f7f",  # gray
]


# ── Main Execution ───────────────────────────────────────────────────
if not selected_presets:
    st.info("사이드바에서 Preset을 선택하거나, Custom Portfolio를 구성하세요.")
else:
    engine = MacroPortfolioEngine()

    with st.spinner("백테스팅 실행 중..."):
        active_ports = {name: PRESETS[name] for name in selected_presets if name in PRESETS}
        results = engine.compare_portfolios(
            active_ports,
            start_date=start_date.strftime("%Y-%m-%d"),
            rebalance_freq=freq_map[rebalance_freq]
        )

        all_hist = pd.DataFrame()
        summary_data = []
        for name, res in results.items():
            if "error" not in res:
                all_hist[name] = res['history']['total_value']
                summary_data.append({
                    "전략": name,
                    "누적수익률": res.get('total_return', 0),
                    "CAGR": res.get('cagr', 0),
                    "MDD": res.get('max_drawdown', 0),
                    "Sharpe": res.get('sharpe_ratio', 0),
                    "Weights": active_ports.get(name, {})
                })
            else:
                st.error(f"{name}: {res['error']}")

        if summary_data:
            # ── Summary Cards ────────────────────────────────────
            st.markdown("### 성과 요약")
            m_cols = st.columns(len(summary_data))
            for i, s in enumerate(summary_data):
                cagr_class = "positive" if s['CAGR'] >= 0 else "negative"
                mdd_class = "negative"
                strategy_label = s['전략']
                with m_cols[i]:
                    st.markdown(f"""
                    <div class="stat-card">
                        <div class="label">{strategy_label}</div>
                        <div class="value">{s['누적수익률']*100:+.1f}%</div>
                        <div class="sub">
                            CAGR <span class="{cagr_class}">{s['CAGR']*100:+.1f}%</span>
                            &middot;
                            MDD <span class="{mdd_class}">{s['MDD']*100:.1f}%</span>
                            &middot;
                            Sharpe {s['Sharpe']:.2f}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            # ── Tabs ─────────────────────────────────────────────
            tab_growth, tab_risk, tab_optimizer = st.tabs(["성장 추이", "리스크", "매크로 최적화"])

            with tab_growth:
                # 혹시 모를 결측치에 대비해 각 전략의 첫 번째 유효 데이터를 기준으로 100으로 정규화
                norm_hist = all_hist.apply(lambda col: (col / col.dropna().iloc[0]) * 100 if not col.dropna().empty else col)
                fig_growth = go.Figure()
                for idx, col in enumerate(norm_hist.columns):
                    fig_growth.add_trace(go.Scatter(
                        x=norm_hist.index,
                        y=norm_hist[col],
                        name=col,
                        line=dict(color=CHART_COLORS[idx % len(CHART_COLORS)], width=1.8),
                        hovertemplate="%{y:.1f}<extra>%{fullData.name}</extra>"
                    ))
                fig_growth.update_layout(
                    title="",
                    height=520,
                    hovermode="x unified",
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    xaxis=dict(
                        gridcolor="#f0f0f0",
                        showgrid=True,
                        zeroline=False,
                        linecolor="#cccccc",
                        tickfont=dict(color="#555555"),
                    ),
                    yaxis=dict(
                        title="상대 가치 (기준 100)",
                        gridcolor="#f0f0f0",
                        showgrid=True,
                        zeroline=False,
                        linecolor="#cccccc",
                        tickfont=dict(color="#555555"),
                        title_font=dict(color="#555555"),
                    ),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="left",
                        x=0,
                        font=dict(size=11, color="#333333")
                    ),
                    margin=dict(l=70, r=40, t=80, b=60),
                    font=dict(family="Noto Sans KR, Inter, sans-serif", color="#333333"),
                )
                st.plotly_chart(fig_growth, use_container_width=True)

            with tab_risk:
                col_l, col_r = st.columns(2)
                with col_l:
                    df_summary = pd.DataFrame(summary_data)
                    fig_scatter = go.Figure()
                    for idx, row in df_summary.iterrows():
                        fig_scatter.add_trace(go.Scatter(
                            x=[abs(row["MDD"]) * 100],
                            y=[row["CAGR"] * 100],
                            mode="markers+text",
                            text=[row["전략"]],
                            textposition="top center",
                            textfont=dict(color="#333333", size=11),
                            marker=dict(
                                size=12,
                                color=CHART_COLORS[idx % len(CHART_COLORS)],
                            ),
                            name=row["전략"],
                            showlegend=False,
                            hovertemplate="MDD: %{x:.1f}%<br>CAGR: %{y:.1f}%<extra></extra>"
                        ))
                    fig_scatter.update_layout(
                        title="CAGR vs 최대낙폭 (MDD)",
                        height=420,
                        plot_bgcolor="#ffffff",
                        paper_bgcolor="#ffffff",
                        xaxis=dict(title="최대낙폭 (%)", gridcolor="#f0f0f0", linecolor="#cccccc", tickfont=dict(color="#555555")),
                        yaxis=dict(title="CAGR (%)", gridcolor="#f0f0f0", linecolor="#cccccc", tickfont=dict(color="#555555")),
                        font=dict(family="Noto Sans KR, Inter, sans-serif", color="#333333"),
                        margin=dict(l=70, r=40, t=80, b=60),
                    )
                    st.plotly_chart(fig_scatter, use_container_width=True)

                with col_r:
                    fig_bar = go.Figure()
                    strategies = df_summary["전략"].tolist()
                    bar_colors = [CHART_COLORS[i % len(CHART_COLORS)] for i in range(len(strategies))]
                    fig_bar.add_trace(go.Bar(
                        name="Sharpe",
                        x=strategies,
                        y=df_summary["Sharpe"],
                        marker_color=bar_colors,
                    ))
                    fig_bar.update_layout(
                        title="Sharpe Ratio",
                        height=420,
                        plot_bgcolor="#ffffff",
                        paper_bgcolor="#ffffff",
                        xaxis=dict(gridcolor="#f0f0f0", linecolor="#cccccc", tickfont=dict(color="#555555")),
                        yaxis=dict(gridcolor="#f0f0f0", linecolor="#cccccc", tickfont=dict(color="#555555")),
                        font=dict(family="Noto Sans KR, Inter, sans-serif", color="#333333"),
                        margin=dict(l=70, r=40, t=80, b=60),
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)

            with tab_optimizer:
                st.markdown("### 매크로 지표 기반 최적 포트폴리오")
                st.markdown('<div class="info-box">현재 매크로 국면(성장·인플레·유동성·스트레스)을 종합 분석하여 '
                            'Mean-Variance Optimization으로 Sharpe Ratio가 최대인 배분을 추천합니다.<br>'
                            '<b>EV(기대값) = 기대수익률 − 무위험이자율 &gt; 0</b>인 배분만 제안합니다.</div>',
                            unsafe_allow_html=True)

                opt_col1, opt_col2 = st.columns([1, 3])
                with opt_col1:
                    lookback = st.selectbox("수익률 산출 기간", [3, 5, 7, 10], index=1, format_func=lambda x: f"{x}년")
                    rf_pct = st.number_input("무위험이자율 (%)", value=4.0, step=0.5, min_value=0.0, max_value=15.0)

                optimizer = MacroOptimizer(rf=rf_pct / 100.0)
                with opt_col2:
                    if st.button("최적 포트폴리오 산출", type="primary"):
                        with st.spinner("매크로 지표 분석 및 최적화 중..."):
                            opt_result = optimizer.recommend(lookback_years=lookback)

                        if "error" in opt_result:
                            st.error(opt_result["error"])
                        else:
                            st.session_state._opt_result = opt_result

                # 결과 표시
                if "_opt_result" in st.session_state:
                    opt_result = st.session_state._opt_result
                    snap = opt_result["regime"]
                    metrics = opt_result["metrics"]

                    # ── 국면 카드 ──
                    regime_colors = {"Goldilocks": "#2e7d32", "Reflation": "#e65100",
                                     "Stagflation": "#c62828", "Deflation": "#1565c0"}
                    regime_labels = {"Goldilocks": "골디락스 (적정성장·저물가)",
                                     "Reflation": "리플레이션 (성장·물가 동반상승)",
                                     "Stagflation": "스태그플레이션 (저성장·고물가)",
                                     "Deflation": "디플레이션 (저성장·저물가)"}
                    r_color = regime_colors.get(snap.regime, "#333")
                    r_label = regime_labels.get(snap.regime, snap.regime)

                    st.markdown(f"""
                    <div style="background:linear-gradient(135deg, {r_color}15, {r_color}08); 
                                border-left: 4px solid {r_color}; border-radius: 6px; 
                                padding: 16px 20px; margin: 12px 0;">
                        <div style="font-size:0.75em; color:#666; text-transform:uppercase; 
                                    font-weight:600; letter-spacing:0.05em;">현재 매크로 국면</div>
                        <div style="font-size:1.4em; font-weight:700; color:{r_color}; margin:4px 0;">
                            {r_label}</div>
                        <div style="font-size:0.82em; color:#555; font-family:'JetBrains Mono',monospace;">
                            CPI YoY: {snap.details.get('cpi_yoy','N/A')}% · 
                            INDPRO YoY: {snap.details.get('indpro_yoy','N/A')}% · 
                            VIX: {snap.details.get('vix','N/A')} · 
                            스트레스: {snap.details.get('stress_score','N/A')}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # ── 국면 진단 근거 ──
                    ind_y = snap.details.get('indpro_yoy', 'N/A')
                    cpi_y = snap.details.get('cpi_yoy', 'N/A')
                    liq_t = snap.details.get('net_liquidity_trend', 'N/A')
                    v_val = snap.details.get('vix', 'N/A')
                    hy_s  = snap.details.get('hy_spread', 'N/A')
                    str_s = snap.details.get('stress_score', 'N/A')
                    
                    def fmt_val(val, suffix=""):
                        if isinstance(val, (int, float)):
                            return f"{val:.2f}{suffix}"
                        return str(val)

                    reasoning_html = f"""
                    <div style="background: #fdfdfd; border: 1px solid #eee; border-radius: 6px; padding: 14px 18px; margin-bottom: 16px;">
                        <div style="font-size: 0.85em; font-weight: 600; color: #444; margin-bottom: 8px;">매크로 상세 근거</div>
                        <div style="display: grid; grid-template-columns: 1fr; gap: 20px;">
                            <ul style="color: #444; font-size: 0.85em; line-height: 1.6; margin: 0; padding-left: 20px;">
                                <li><b>성장(INDPRO)</b>: 전년비 {fmt_val(ind_y, '%')}</li>
                                <li><b>물가(CPI)</b>: 전년비 {fmt_val(cpi_y, '%')}</li>
                                <li><b>유동성</b>: 추세 {fmt_val(liq_t)}</li>
                                <li><b>스트레스</b>: VIX {fmt_val(v_val)} ({fmt_val(str_s)})</li>
                            </ul>
                        </div>
                        <div style="font-size: 0.82em; color: #666; margin-top: 12px; border-top: 1px solid #f0f0f0; padding-top: 8px;">
                            현재 <b>{r_label}</b> 국면을 고려하여, 기대수익(EV>0) 및 위험 대비 수익률을 극대화하는 최적 비중을 산출했습니다.
                        </div>
                    </div>
                    """
                    st.markdown(reasoning_html, unsafe_allow_html=True)

                    # ── 핵심 지표 카드 ──
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    ev_class = "positive" if metrics['ev'] > 0 else "negative"
                    with mc1:
                        st.markdown(f'<div class="stat-card"><div class="label">기대 수익률</div>'
                                    f'<div class="value">{metrics["expected_return"]:+.1f}%</div></div>',
                                    unsafe_allow_html=True)
                    with mc2:
                        st.markdown(f'<div class="stat-card"><div class="label">변동성</div>'
                                    f'<div class="value">{metrics["volatility"]:.1f}%</div></div>',
                                    unsafe_allow_html=True)
                    with mc3:
                        st.markdown(f'<div class="stat-card"><div class="label">샤프 지수 (Sharpe)</div>'
                                    f'<div class="value">{metrics["sharpe"]:.3f}</div></div>',
                                    unsafe_allow_html=True)
                    with mc4:
                        st.markdown(f'<div class="stat-card"><div class="label">기대값 (초과수익)</div>'
                                    f'<div class="value"><span class="{ev_class}">{metrics["ev"]:+.1f}%</span></div></div>',
                                    unsafe_allow_html=True)

                    # ── 차트: 파이 + Efficient Frontier ──
                    chart_l, chart_r = st.columns(2)
                    with chart_l:
                        w_data = opt_result["weights"]
                        fig_pie = go.Figure(data=[go.Pie(
                            labels=list(w_data.keys()),
                            values=[v * 100 for v in w_data.values()],
                            textinfo="label+percent",
                            textfont=dict(size=12),
                            marker=dict(colors=CHART_COLORS[:len(w_data)]),
                            hole=0.4,
                        )])
                        fig_pie.update_layout(
                            title="최적 자산배분",
                            height=400,
                            plot_bgcolor="#ffffff",
                            paper_bgcolor="#ffffff",
                            font=dict(family="Noto Sans KR, Inter, sans-serif", color="#333"),
                            margin=dict(l=40, r=40, t=80, b=40),
                            showlegend=False,
                        )
                        st.plotly_chart(fig_pie, use_container_width=True)

                    with chart_r:
                        ef = opt_result.get("efficient_frontier", [])
                        if ef:
                            ef_df = pd.DataFrame(ef)
                            fig_ef = go.Figure()
                            
                            # Efficient Frontier Line
                            fig_ef.add_trace(go.Scatter(
                                x=ef_df["volatility"], y=ef_df["return"],
                                mode="lines",
                                name="효율적투자선",
                                line=dict(color="#1f77b4", width=2),
                            ))

                            # CML (Capital Market Line)
                            cml_data = opt_result.get("cml", [])
                            if cml_data:
                                cml_df = pd.DataFrame(cml_data)
                                fig_ef.add_trace(go.Scatter(
                                    x=cml_df["volatility"], y=cml_df["return"],
                                    mode="lines",
                                    name="자본시장선 (CML)",
                                    line=dict(color="rgba(0,0,0,0.3)", width=1, dash="dash"),
                                ))

                            # 최적점 마커
                            fig_ef.add_trace(go.Scatter(
                                x=[metrics["volatility"]], y=[metrics["expected_return"]],
                                mode="markers+text",
                                text=["최적점"],
                                textposition="top center",
                                marker=dict(size=12, color="#d62728", symbol="star"),
                                name="최적 포트폴리오",
                                showlegend=True,
                            ))

                            # 커스텀 포트폴리오 분석 및 차트 추가
                            for p_name, p_weights in active_ports.items():
                                # 커스텀 포트폴리오 성능 분석
                                custom_analysis = optimizer.analyze_custom_portfolio(p_weights, lookback_years=lookback)
                                if "error" not in custom_analysis:
                                    fig_ef.add_trace(go.Scatter(
                                        x=[custom_analysis["volatility"]], y=[custom_analysis["expected_return"]],
                                        mode="markers+text",
                                        text=[p_name],
                                        textposition="bottom center",
                                        marker=dict(size=10, color="rgba(79, 70, 229, 0.8)", symbol="circle"),
                                        name=f"커스텀: {p_name}",
                                        hovertemplate=f"<b>{p_name}</b><br>수익률: {custom_analysis['expected_return']}%<br>변동성: {custom_analysis['volatility']}%<br>Sharpe: {custom_analysis['sharpe']}<extra></extra>"
                                    ))

                            # 개별 자산 마커
                            for ast in opt_result.get("asset_stats", []):
                                fig_ef.add_trace(go.Scatter(
                                    x=[ast["volatility"]], y=[ast["expected_return"]],
                                    mode="markers+text",
                                    text=[ast["ticker"]],
                                    textposition="top center",
                                    textfont=dict(size=10, color="#888"),
                                    marker=dict(size=8, color="#999", opacity=0.4),
                                    name=ast["ticker"],
                                    showlegend=False,
                                    hovertemplate=f"{ast['ticker']}<br>수익률: {ast['expected_return']:.1f}%<br>변동성: {ast['volatility']:.1f}%<extra></extra>",
                                ))
                            fig_ef.update_layout(
                                title="효율적투자선 및 자본시장선(CML)",
                                height=550,
                                plot_bgcolor="#ffffff",
                                paper_bgcolor="#ffffff",
                                xaxis=dict(title="변동성 (%)", gridcolor="#f0f0f0", linecolor="#ccc", tickfont=dict(color="#555")),
                                yaxis=dict(title="기대수익률 (%)", gridcolor="#f0f0f0", linecolor="#ccc", tickfont=dict(color="#555")),
                                font=dict(family="Pretendard, sans-serif", color="#333"),
                                margin=dict(l=70, r=40, t=100, b=60),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                            st.plotly_chart(fig_ef, use_container_width=True)

                    # ── 상세 테이블 ──
                    st.markdown("#### 자산별 상세")
                    ast_df = pd.DataFrame(opt_result.get("asset_stats", []))
                    if not ast_df.empty:
                        ast_df.columns = ["티커", "기대수익률 (%)", "변동성 (%)", "비중 (%)"]
                        st.dataframe(ast_df.set_index("티커"), use_container_width=True)

                    # ── 백테스트에 적용 버튼 ──
                    st.markdown("---")
                    if st.button("이 포트폴리오로 백테스트 비교에 추가"):
                        opt_weights = opt_result["weights"]
                        opt_name = f"Macro Optimal ({snap.regime})"
                        st.session_state.custom_presets[opt_name] = opt_weights
                        st.session_state._pending_preset = opt_name
                        st.rerun()

            # ── Detailed Table ───────────────────────────────────
            st.markdown("### 상세 통계")
            stats_df = pd.DataFrame(summary_data).set_index("전략")
            display_df = stats_df.drop(columns=["Weights"], errors="ignore").copy()
            for col in ['누적수익률', 'CAGR', 'MDD']:
                if col in display_df.columns:
                    display_df[col] = display_df[col].map('{:.2%}'.format)
            for col in ['Sharpe']:
                if col in display_df.columns:
                    display_df[col] = display_df[col].map('{:.2f}'.format)
            st.dataframe(display_df, use_container_width=True)

            # ── Export ───────────────────────────────────────────
            st.markdown("---")
            col_share, col_notion = st.columns(2)
            with col_share:
                st.markdown("#### 임베드")
                share_url = "http://localhost:8501/Portfolio_Compare?embed=true"
                st.code(share_url, language=None)
                st.caption("Notion에서 /embed 명령어로 이 URL을 붙여넣으면 대시보드를 인라인으로 표시할 수 있습니다.")

            with col_notion:
                st.markdown("#### Notion 내보내기")
                if st.button("보고서 전송"):
                    from analysis.notion_exporter import NotionExporter
                    exporter = NotionExporter()
                    with st.spinner("내보내는 중..."):
                        success_count = 0
                        for s in summary_data:
                            url = exporter.create_report_page(
                                s['전략'], s, "포트폴리오 대시보드에서 내보냄."
                            )
                            if url:
                                success_count += 1
                        if success_count > 0:
                            st.success(f"{success_count}개 전략이 내보내졌습니다.")
                        else:
                            st.error("내보내기 실패. Notion API 설정을 확인하세요.")
        else:
            st.warning("결과가 없습니다. 티커 유효성 또는 시작일을 확인하세요.")
