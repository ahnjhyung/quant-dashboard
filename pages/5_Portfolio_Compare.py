import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from analysis.macro_portfolio_engine import MacroPortfolioEngine
from data_collectors.macro_backfiller import MacroBackfiller
from datetime import datetime
import numpy as np
import yfinance as yf

# Page Config
st.set_page_config(page_title="포트폴리오 분석기", layout="wide")

# Notion Embed Detection
is_embed = st.query_params.get("embed", "false").lower() == "true"

# ── Styling: Clean White Theme ───────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"],
[data-testid="stHeader"], .main {
    font-family: 'Noto Sans KR', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
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
    st.markdown("## 포트폴리오 비교 분석")
    st.caption("멀티에셋 포트폴리오 백테스팅 및 리스크 분석")


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
    start_date = st.date_input("시작일", datetime(2010, 1, 1))
    rebalance_freq = st.selectbox(
        "Rebalancing",
        ["Monthly (ME)", "Quarterly (QE)", "Yearly (YE)"],
        index=0
    )
    freq_map = {"Monthly (ME)": "ME", "Quarterly (QE)": "QE", "Yearly (YE)": "YE"}

    st.markdown("---")

    # Preset Selection
    PRESETS = {
        "Classic 60/40": {"SPY": 0.6, "TLT": 0.4},
        "All Weather": {"SPY": 0.30, "TLT": 0.40, "IEF": 0.15, "GLD": 0.075, "GSG": 0.075},
        "Permanent": {"SPY": 0.25, "TLT": 0.25, "GLD": 0.25, "SHY": 0.25},
        "Golden Butterfly": {"SPY": 0.2, "IWM": 0.2, "TLT": 0.2, "IEF": 0.2, "GLD": 0.2},
        "S&P 500 Only": {"SPY": 1.0}
    }

    selected_presets = st.multiselect(
        "Preset Strategies",
        list(PRESETS.keys()),
        default=["Classic 60/40", "All Weather", "S&P 500 Only"]
    )

    with st.expander("📚 전략 설명 보기"):
        st.markdown("""
        - **Permanent (영구 포트폴리오)**: 
          주식(SPY), 장기채(TLT), 현금(SHY), 금(GLD)에 각각 **25%씩** 배분하는 전략입니다. 경제의 4계절(호황/불황/인플레/디플레)을 모두 방어하기 위해 설계된 초저변동성 전략입니다.
        - **Golden Butterfly**: 
          영구 포트폴리오를 기반으로 수익성을 강화한 전략입니다. 대형주(SPY) 20%, 소형주(IWM) 20%, 장기채(TLT) 20%, 단기채(IEF) 20%, 금(GLD) 20%로 구성됩니다.
        - **All Weather (사계절 포트폴리오)**: 
          레이 달리오가 고안한 전략으로 주식 30%, 중기채 15%, 장기채 40%, 금 7.5%, 원자재 7.5%로 구성됩니다. 각 자산의 리스크(변동성) 비중을 균등하게 맞추어 어떤 경제 상황에서도 안정적인 우상향을 목표로 합니다.
        """)

    st.markdown("---")
    st.caption(f"v3.0 | {datetime.now().strftime('%Y-%m-%d')}")


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
        st.markdown("#### Build Strategy")
        c_name = st.text_input("Name", "My Strategy")
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
                    PRESETS[c_name] = dict(zip(tickers, weights))
                    if c_name not in selected_presets:
                        selected_presets.append(c_name)
                    st.success(f"'{c_name}' 전략이 추가되었습니다.")
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
            tab_growth, tab_risk = st.tabs(["성장 추이", "리스크"])

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
                    margin=dict(l=0, r=0, t=30, b=0),
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
                            x=[row["MDD"] * 100],
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
                        margin=dict(l=0, r=0, t=40, b=0),
                    )
                    st.plotly_chart(fig_scatter, use_container_width=True)

                with col_r:
                    fig_bar = go.Figure()
                    strategies = df_summary["전략"].tolist()
                    fig_bar.add_trace(go.Bar(
                        name="Sharpe",
                        x=strategies,
                        y=df_summary["Sharpe"],
                        marker_color="#1f77b4",
                    ))
                    fig_bar.update_layout(
                        title="Sharpe Ratio",
                        height=420,
                        plot_bgcolor="#ffffff",
                        paper_bgcolor="#ffffff",
                        xaxis=dict(gridcolor="#f0f0f0", linecolor="#cccccc", tickfont=dict(color="#555555")),
                        yaxis=dict(gridcolor="#f0f0f0", linecolor="#cccccc", tickfont=dict(color="#555555")),
                        font=dict(family="Noto Sans KR, Inter, sans-serif", color="#333333"),
                        margin=dict(l=0, r=0, t=40, b=0),
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)

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
