"""
Fundamental & Swing Analysis Dashboard
=======================================
개별 종목 분석: 가치투자(DCF, F-Score) + 기술적 분석(RSI, MACD, 볼린저밴드)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

st.set_page_config(page_title="Fundamental & Swing", layout="wide")

# ── CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap');
* { font-family: 'Noto Sans KR', 'Inter', sans-serif; }
[data-testid="stAppViewContainer"] { background-color: #ffffff; }
[data-testid="stSidebar"] { background-color: #fafafa; border-right: 1px solid #e5e5e5; }
h1, h2, h3 { color: #111111; font-weight: 600; }
.stMarkdown p, .stMarkdown li { color: #333333; }

.metric-card {
    background: #fafafa;
    border: 1px solid #e8e8e8;
    border-radius: 8px;
    padding: 16px;
    text-align: center;
}
.metric-card .label { font-size: 12px; color: #888; font-weight: 500; }
.metric-card .value { font-size: 22px; font-weight: 700; color: #111; margin: 4px 0; }
.metric-card .sub { font-size: 11px; color: #666; }

.signal-buy { color: #2e7d32; font-weight: 700; }
.signal-sell { color: #d32f2f; font-weight: 700; }
.signal-hold { color: #f57c00; font-weight: 700; }

.score-bar {
    background: #e8e8e8;
    border-radius: 4px;
    height: 8px;
    margin: 4px 0;
}
.score-fill {
    height: 8px;
    border-radius: 4px;
}
</style>
""", unsafe_allow_html=True)


# ── Title ────────────────────────────────────────────────────────────
st.markdown("# Fundamental & Swing Analysis")
st.markdown("개별 종목의 가치 분석(DCF, F-Score)과 기술적 분석(RSI, MACD, 볼린저밴드)을 통합 제공합니다.")


# ── Session State Init ───────────────────────────────────────────────
if "fs_mode" not in st.session_state:
    st.session_state.fs_mode = None

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Mode")
    mode = st.radio(
        "분석 모드 선택",
        ["종목 분석", "종목 비교 (Multi-Screen)", "Macro Dashboard"],
        index=0, label_visibility="collapsed"
    )
    st.session_state.fs_mode = mode

    st.markdown("---")

    if mode == "종목 분석":
        st.markdown("### 종목 분석")
        ticker_input = st.text_input(
            "Ticker",
            value="AAPL",
            help="Yahoo Finance 티커를 입력하세요 (예: AAPL, MSFT, 005930.KS)"
        )
        analysis_period = st.selectbox(
            "분석 기간",
            ["6mo", "1y", "2y", "5y"],
            index=1,
            format_func=lambda x: {"6mo": "6개월", "1y": "1년", "2y": "2년", "5y": "5년"}[x]
        )
        run_analysis = st.button("분석 실행", use_container_width=True)
    else:
        ticker_input = ""
        analysis_period = "1y"
        run_analysis = False

    if mode == "종목 비교 (Multi-Screen)":
        st.markdown("### 종목 비교")
        st.caption("여러 종목의 재무 지표를 한 번에 비교합니다.")
        screen_tickers = st.text_area(
            "종목 리스트 (쉼표 구분)",
            "AAPL, MSFT, GOOG, AMZN, META, NVDA, TSLA, JPM",
            help="Magic Formula 순위 및 가치 지표 비교 대상"
        )
        run_screening = st.button("비교 실행", use_container_width=True)
    else:
        screen_tickers = ""
        run_screening = False

    # Macro mode has no sidebar inputs needed
    run_macro = (mode == "Macro Dashboard")

    st.markdown("---")
    st.caption(f"v3.0 | {datetime.now().strftime('%Y-%m-%d')}")


# ── Analysis Engine Import ───────────────────────────────────────────
from analysis.value_investing import ValueInvestingAnalyzer
from analysis.swing_trading import SwingTradingAnalyzer
from data_collectors.supabase_manager import SupabaseManager

value_analyzer = ValueInvestingAnalyzer()
swing_analyzer = SwingTradingAnalyzer()
db = SupabaseManager()


FONT_FAMILY = "Noto Sans KR, Inter, sans-serif"
CHART_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]


# ── Individual Analysis ─────────────────────────────────────────────
if run_analysis and ticker_input:
    ticker = ticker_input.strip().upper()

    with st.spinner(f"{ticker} 분석 중..."):
        # 가치 분석
        fscore_data = value_analyzer.piotroski_score(ticker)
        dcf_data = value_analyzer.dcf_valuation(ticker)
        full_value = value_analyzer.full_value_analysis(ticker)

        # 기술적 분석
        swing_data = swing_analyzer.full_analysis(ticker, period=analysis_period)

    if "error" in swing_data:
        st.error(f"기술적 분석 실패: {swing_data['error']}")
    else:
        # ── Header Metrics ───────────────────────────────────
        st.markdown(f"## {ticker} 종합 분석")

        col1, col2, col3, col4, col5 = st.columns(5)

        current_price = swing_data.get('current_price', 0)
        signal = swing_data.get('swing_signal', 'HOLD')
        confidence = swing_data.get('confidence', 0)
        ev_pct = full_value.get('expected_value_pct', 0)
        fscore = fscore_data.get('score', 0)

        signal_class = "signal-buy" if "BUY" in signal else ("signal-sell" if "SELL" in signal else "signal-hold")
        signal_clean = signal.replace(" 🟢", "").replace(" 🔴", "").replace(" 🟡", "")

        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="label">현재가</div>
                <div class="value">${current_price:,.2f}</div>
                <div class="sub">{swing_data.get('analysis_date', '')}</div>
            </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="label">Swing Signal</div>
                <div class="value {signal_class}">{signal_clean}</div>
                <div class="sub">신뢰도 {confidence*100:.0f}%</div>
            </div>
            """, unsafe_allow_html=True)

        with col3:
            ev_color = "signal-buy" if ev_pct > 0 else "signal-sell"
            st.markdown(f"""
            <div class="metric-card">
                <div class="label">Expected Value</div>
                <div class="value {ev_color}">{ev_pct:+.2f}%</div>
                <div class="sub">EV > 0 = 진입 가능</div>
            </div>
            """, unsafe_allow_html=True)

        with col4:
            score_color = "#2e7d32" if fscore >= 7 else ("#f57c00" if fscore >= 4 else "#d32f2f")
            score_pct = fscore / 9 * 100
            st.markdown(f"""
            <div class="metric-card">
                <div class="label">F-Score</div>
                <div class="value" style="color:{score_color}">{fscore}/9</div>
                <div class="score-bar"><div class="score-fill" style="width:{score_pct}%;background:{score_color}"></div></div>
            </div>
            """, unsafe_allow_html=True)

        with col5:
            intrinsic = dcf_data.get('intrinsic_value_per_share', 0)
            margin = dcf_data.get('margin_of_safety', 0) * 100
            margin_color = "signal-buy" if margin > 0 else "signal-sell"
            if "error" in dcf_data:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="label">DCF 내재가치</div>
                    <div class="value" style="font-size:14px; color:#999">데이터 없음</div>
                    <div class="sub">FCF 수동 입력 필요</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="label">DCF 내재가치</div>
                    <div class="value">${intrinsic:,.2f}</div>
                    <div class="sub {margin_color}">안전마진 {margin:+.1f}%</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")

        # ── Chart: Price + Technical Indicators ──────────────
        tab_chart, tab_fundamental, tab_risk = st.tabs(["기술적 분석", "가치 분석", "리스크 관리"])

        with tab_chart:
            ohlcv = swing_data.get('ohlcv', pd.DataFrame())
            if not ohlcv.empty:
                close = ohlcv['Close']
                rsi_series = swing_analyzer.calculate_rsi(close)
                macd_line, signal_line, histogram = swing_analyzer.calculate_macd(close)
                upper, middle, lower, bw, pct_b = swing_analyzer.bollinger_bands(close)

                fig = make_subplots(
                    rows=3, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.04,
                    row_heights=[0.55, 0.22, 0.23],
                    subplot_titles=["", "RSI", "MACD"]
                )

                # Price + Bollinger
                fig.add_trace(go.Scatter(x=ohlcv.index, y=close, name="종가",
                    line=dict(color="#333", width=1.5)), row=1, col=1)
                fig.add_trace(go.Scatter(x=ohlcv.index, y=upper, name="상단밴드",
                    line=dict(color="#aaa", width=0.8, dash="dot")), row=1, col=1)
                fig.add_trace(go.Scatter(x=ohlcv.index, y=lower, name="하단밴드",
                    line=dict(color="#aaa", width=0.8, dash="dot"),
                    fill="tonexty", fillcolor="rgba(200,200,200,0.1)"), row=1, col=1)
                fig.add_trace(go.Scatter(x=ohlcv.index, y=middle, name="SMA(20)",
                    line=dict(color="#1f77b4", width=0.8)), row=1, col=1)

                # EMA 200
                ema200 = swing_analyzer.calculate_ema(close, 200)
                fig.add_trace(go.Scatter(x=ohlcv.index, y=ema200, name="EMA(200)",
                    line=dict(color="#ff7f0e", width=1.2, dash="dash")), row=1, col=1)

                # RSI
                fig.add_trace(go.Scatter(x=ohlcv.index, y=rsi_series, name="RSI",
                    line=dict(color="#9467bd", width=1.2)), row=2, col=1)
                fig.add_hline(y=70, line_dash="dot", line_color="#d32f2f", line_width=0.8, row=2, col=1)
                fig.add_hline(y=30, line_dash="dot", line_color="#2e7d32", line_width=0.8, row=2, col=1)

                # MACD
                colors = ["#2e7d32" if v >= 0 else "#d32f2f" for v in histogram]
                fig.add_trace(go.Bar(x=ohlcv.index, y=histogram, name="Histogram",
                    marker_color=colors), row=3, col=1)
                fig.add_trace(go.Scatter(x=ohlcv.index, y=macd_line, name="MACD",
                    line=dict(color="#1f77b4", width=1)), row=3, col=1)
                fig.add_trace(go.Scatter(x=ohlcv.index, y=signal_line, name="Signal",
                    line=dict(color="#ff7f0e", width=1)), row=3, col=1)

                fig.update_layout(
                    height=700,
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    font=dict(family=FONT_FAMILY, color="#333"),
                    legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10)),
                    margin=dict(l=0, r=0, t=30, b=0),
                    hovermode="x unified",
                )
                for i in range(1, 4):
                    fig.update_xaxes(gridcolor="#f0f0f0", linecolor="#ccc", row=i, col=1)
                    fig.update_yaxes(gridcolor="#f0f0f0", linecolor="#ccc", row=i, col=1)

                st.plotly_chart(fig, use_container_width=True)

                # Signal details table
                st.markdown("#### 신호 상세")
                sig_data = swing_data.get('signals', {})
                if sig_data:
                    rows = []
                    for indicator, info in sig_data.items():
                        rows.append({
                            "지표": indicator,
                            "신호": info.get('signal', ''),
                            "값": f"{info.get('value', 0):.2f}",
                            "근거": info.get('reason', '')
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else:
                    st.caption("현재 활성화된 신호가 없습니다.")

        with tab_fundamental:
            col_f1, col_f2 = st.columns(2)

            with col_f1:
                st.markdown("#### Piotroski F-Score 상세")
                details = fscore_data.get('details', {})
                if details:
                    f_rows = []
                    labels = {
                        'F1_ROA_positive': 'ROA > 0 (수익성)',
                        'F2_OCF_positive': '영업현금흐름 > 0',
                        'F3_ROA_improved': 'ROA 개선',
                        'F4_accruals_low': '발생항목 양호',
                        'F5_leverage_decreased': '부채비율 < 100%',
                        'F6_liquidity_improved': '유동비율 > 1.5',
                        'F7_no_dilution': '신주 발행 없음',
                        'F8_gross_margin_improved': '매출총이익률 > 20%',
                        'F9_asset_turnover_improved': '자산회전율 양호',
                    }
                    for key, passed in details.items():
                        f_rows.append({
                            "항목": labels.get(key, key),
                            "결과": "PASS" if passed else "FAIL",
                        })
                    df_f = pd.DataFrame(f_rows)
                    st.dataframe(df_f, use_container_width=True, hide_index=True)

                st.markdown("#### 기본 재무 지표")
                fin_metrics = {
                    "PER": fscore_data.get('per', '-'),
                    "PBR": fscore_data.get('pbr', '-'),
                    "ROE (%)": f"{fscore_data.get('roe', 0):.1f}",
                    "유동비율": fscore_data.get('current_ratio', '-'),
                    "부채비율": fscore_data.get('debt_to_equity', '-'),
                }
                st.dataframe(
                    pd.DataFrame([fin_metrics]),
                    use_container_width=True,
                    hide_index=True
                )

            with col_f2:
                st.markdown("#### DCF Valuation")
                if "error" not in dcf_data:
                    dcf_metrics = {
                        "FCF (base)": f"${dcf_data.get('fcf_base', 0):,.0f}",
                        "내재가치 (주당)": f"${dcf_data.get('intrinsic_value_per_share', 0):,.2f}",
                        "현재가": f"${dcf_data.get('current_price', 0):,.2f}",
                        "안전마진": f"{dcf_data.get('margin_of_safety', 0)*100:+.1f}%",
                        "Upside": f"{dcf_data.get('upside_pct', 0):+.1f}%",
                    }
                    for k, v in dcf_metrics.items():
                        st.markdown(f"**{k}:** {v}")

                    # DCF projection chart
                    projected = dcf_data.get('projected_fcf', [])
                    pv = dcf_data.get('pv_fcf', [])
                    if projected:
                        fig_dcf = go.Figure()
                        years = list(range(1, len(projected) + 1))
                        fig_dcf.add_trace(go.Bar(
                            x=years, y=[f/1e9 for f in projected],
                            name="FCF (10억$)", marker_color="#1f77b4"
                        ))
                        fig_dcf.add_trace(go.Bar(
                            x=years, y=[f/1e9 for f in pv],
                            name="PV (10억$)", marker_color="#ff7f0e"
                        ))
                        fig_dcf.update_layout(
                            title="DCF 예측 현금흐름",
                            height=350,
                            barmode="group",
                            plot_bgcolor="#fff", paper_bgcolor="#fff",
                            font=dict(family=FONT_FAMILY, color="#333"),
                            xaxis=dict(title="연도", gridcolor="#f0f0f0"),
                            yaxis=dict(title="10억 $", gridcolor="#f0f0f0"),
                            margin=dict(l=0, r=0, t=40, b=0),
                        )
                        st.plotly_chart(fig_dcf, use_container_width=True)
                else:
                    st.caption("DCF 데이터를 가져올 수 없습니다. FCF를 수동 입력하세요.")

                st.markdown("#### EV (기대값) 산출")
                ev_data = full_value
                if ev_data:
                    ev_metrics = {
                        "추정 승률": f"{ev_data.get('win_probability', 0)*100:.1f}%",
                        "평균 이익률": f"+{ev_data.get('avg_profit_pct', 0):.1f}%",
                        "평균 손실률": f"-{ev_data.get('avg_loss_pct', 0):.1f}%",
                        "Expected Value": f"{ev_data.get('expected_value_pct', 0):+.2f}%",
                    }
                    for k, v in ev_metrics.items():
                        st.markdown(f"**{k}:** {v}")
                    if ev_data.get('expected_value_pct', 0) > 0:
                        st.success("EV > 0: 진입 가능 조건 충족")
                    else:
                        st.warning("EV <= 0: 진입 보류 권고")

        with tab_risk:
            rm = swing_data.get('risk_management', {})
            col_r1, col_r2 = st.columns(2)

            with col_r1:
                st.markdown("#### ATR 기반 리스크 관리")
                risk_items = {
                    "진입가": f"${rm.get('entry', 0):,.2f}",
                    "손절가 (2xATR)": f"${rm.get('stop_loss', 0):,.2f}",
                    "목표가 (3xATR)": f"${rm.get('target', 0):,.2f}",
                    "위험률": f"{rm.get('risk_pct', 0):.2f}%",
                    "Risk/Reward": f"1:{rm.get('risk_reward_ratio', 0):.1f}",
                }
                for k, v in risk_items.items():
                    st.markdown(f"**{k}:** {v}")

            with col_r2:
                st.markdown("#### 추세 분석")
                cross = swing_data.get('ma_cross', {})
                trend_items = {
                    "MA(50)": f"${cross.get('ma50', 0):,.2f}" if cross.get('ma50') else "N/A",
                    "MA(200)": f"${cross.get('ma200', 0):,.2f}" if cross.get('ma200') else "N/A",
                    "EMA(200)": f"${cross.get('ema200', 0):,.2f}" if cross.get('ema200') else "N/A",
                    "200 EMA 위": "Yes" if cross.get('price_above_ema200') else "No",
                    "추세 상태": cross.get('trend_status', 'N/A'),
                    "마지막 골든크로스": cross.get('last_golden_cross', 'N/A'),
                    "마지막 데드크로스": cross.get('last_dead_cross', 'N/A'),
                }
                for k, v in trend_items.items():
                    st.markdown(f"**{k}:** {v}")


# ── Screening (종목 비교) ──────────────────────────────────────────────
if run_screening and screen_tickers:
    tickers = [t.strip().upper() for t in screen_tickers.split(",") if t.strip()]

    st.markdown("---")
    st.markdown("## 종목 비교 결과")

    with st.expander("📊 지표 설명 보기", expanded=False):
        st.markdown("""
| 지표 | 설명 | 해석 |
|:---|:---|:---|
| **PER** | 주가수익비율 (Price/Earnings) | 낮을수록 저평가. 일반적으로 15 이하가 저평가 영역 |
| **PBR** | 주가순자산비율 (Price/Book) | 낮을수록 자산 대비 저평가. 1 미만이면 순자산 이하 거래 |
| **ROE** | 자기자본이익률 (%) | 높을수록 수익성 좋음. 15% 이상이면 우수 |
| **EY (Earnings Yield)** | 이익수익률 = 1/PER | 높을수록 저평가. 채권 금리와 비교 가능 |
| **ROC** | 투하자본수익률 (Return on Capital) | 투입 자본 대비 수익성. 높을수록 효율적 기업 |
| **D/E Ratio** | 부채비율 (Debt/Equity) | 낮을수록 재무 건전성 양호. 1 이하 권장 |
| **Dividend %** | 배당수익률 | 높을수록 현금흐름 좋음. 2~5%가 일반적 |
| **Magic Formula Rank** | EY + ROC 종합 순위 | 낮을수록 좋음 (저평가 + 고품질) |
| **Score / Grade** | 가치투자 종합 평가 (100점 만점) | ROE(30%), PER(25%), PBR(20%), D/E(15%), 배당(10%) 등 5가지 지표를 가중 평가. 80점 이상 S, 65점 이상 A |
        """)

    tab_magic, tab_value = st.tabs(["Magic Formula", "Value Screen"])

    with tab_magic:
        with st.spinner("Magic Formula 순위 계산 중..."):
            try:
                magic_results = value_analyzer.magic_formula_rank(tickers)
                if magic_results:
                    df_magic = pd.DataFrame(magic_results)
                    display_cols = ['ticker', 'combined_rank', 'ey_rank', 'roc_rank',
                                    'earnings_yield', 'roc', 'per', 'pbr', 'roe']
                    display_cols = [c for c in display_cols if c in df_magic.columns]
                    df_display = df_magic[display_cols].copy()
                    df_display.columns = ['Ticker', 'Combined Rank', 'EY Rank', 'ROC Rank',
                                          'Earnings Yield (%)', 'ROC (%)', 'PER', 'PBR', 'ROE (%)'][:len(display_cols)]
                    st.dataframe(
                        df_display.style.format({
                            'Earnings Yield (%)': '{:.2f}',
                            'ROC (%)': '{:.2f}',
                            'PER': '{:.2f}',
                            'PBR': '{:.2f}',
                            'ROE (%)': '{:.2f}'
                        }, na_rep="N/A"),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.caption("결과 없음")
            except Exception as e:
                st.error(f"Magic Formula 오류: {e}")

    with tab_value:
        with st.spinner("가치 스크리닝 중..."):
            try:
                value_results = value_analyzer.value_screen(tickers)
                if value_results:
                    df_val = pd.DataFrame(value_results)
                    display_cols = ['ticker', 'name', 'score', 'grade', 'per', 'pbr', 'roe',
                                    'debt_to_equity', 'dividend_yield', 'sector']
                    display_cols = [c for c in display_cols if c in df_val.columns]
                    df_vdisplay = df_val[display_cols].copy()
                    df_vdisplay.columns = ['Ticker', 'Name', 'Score (100)', 'Grade', 'PER', 'PBR', 'ROE (%)',
                                           'D/E Ratio', 'Dividend %', 'Sector'][:len(display_cols)]
                    
                    st.dataframe(
                        df_vdisplay.style.format({
                            'Score (100)': "{:.1f}",
                        }),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.caption("결과 없음")
            except Exception as e:
                st.error(f"Value Screen 오류: {e}")


# ── Macro Dashboard ──────────────────────────────────────────────────
if run_macro:
    st.markdown("---")
    st.markdown("## Macro Indicators Dashboard")
    st.markdown("Supabase `macro_indicators` 테이블에서 FRED/yfinance 데이터를 조회합니다.")

    MACRO_GROUPS = {
        "금리 / 수익률곡선": ["DGS2", "DGS10", "T10Y2Y", "T10Y3M", "GS10"],
        "유동성": ["M2SL", "WALCL", "RRPONTSYD", "NET_LIQUIDITY"],
        "물가 / 인플레이션": ["CPIAUCSL", "PCEPI", "T5YIE", "REAINTRATREARAT10Y"],
        "스트레스 / 리스크": ["VIXCLS", "NFCI", "TEDRATE", "BAMLH0A0HYM2"],
        "실물 경제": ["UNRATE", "PAYEMS", "INDPRO", "GDP"],
        "시장 자산": ["BTC-USD", "GC=F", "CL=F", "DX-Y.NYB"],
    }

    MACRO_DESCRIPTIONS = {
        "DGS2": "미국 2년 국채 금리 — 단기 금리 기대 반영",
        "DGS10": "미국 10년 국채 금리 — 장기 금리의 벤치마크",
        "T10Y2Y": "10Y-2Y 스프레드 — 역전 시(음수) 경기침체 선행 신호",
        "T10Y3M": "10Y-3M 스프레드 — 가장 신뢰도 높은 경기침체 예측 지표",
        "GS10": "10년 국채 월평균 — 추세 확인용",
        "M2SL": "M2 통화량 — 시장에 풀린 돈의 총량",
        "WALCL": "Fed 총자산 — 양적완화(QE) 규모 추적",
        "RRPONTSYD": "역레포(Reverse Repo) — 단기 유동성 흡수 규모",
        "NET_LIQUIDITY": "순유동성 = Fed자산 - 재무부잔고 - 역레포 — 시장 실질 유동성",
        "CPIAUCSL": "소비자물가지수(CPI) — 인플레이션 핵심 지표",
        "PCEPI": "PCE 물가지수 — Fed가 선호하는 인플레이션 측정치",
        "T5YIE": "5년 기대인플레이션 — 시장이 예상하는 향후 인플레",
        "REAINTRATREARAT10Y": "10년 실질금리 — 명목금리 - 인플레이션",
        "VIXCLS": "VIX 공포지수 — S&P500 옵션 내재변동성",
        "NFCI": "금융여건지수 — 음수=완화, 양수=긴축",
        "TEDRATE": "TED 스프레드 — 은행 간 신용 리스크 척도",
        "BAMLH0A0HYM2": "HY 스프레드 — 정크본드 위험 프리미엄",
        "UNRATE": "실업률 — 노동시장 건전성",
        "PAYEMS": "비농 취업자 수 — 경기 동행 지표",
        "INDPRO": "산업생산지수 — 제조업 활동 측정",
        "GDP": "국내옵생산 — 경제 규모의 총괄 지표",
        "BTC-USD": "비트코인 — 암호화폐 대표 자산",
        "GC=F": "금 선물 — 안전자산 / 인플레 헤지",
        "CL=F": "원유 선물(WTI) — 에너지 / 인플레 선행",
        "DX-Y.NYB": "달러 인덱스(DXY) — 달러 강세 측정",
        "BUFFET_INDICATOR": "버핏 지수 = S&P500/GDP×100 — 시장 과열/저평가 판단",
    }

    # Latest values card row
    with st.spinner("매크로 데이터 로딩 중..."):
        latest = db.get_latest_macro()

    if latest:
        st.markdown("### 주요 지표 현재값")
        cols = st.columns(6)
        display_keys = [("DGS10", "미국 10년 금리", "%"), ("T10Y2Y", "10Y-2Y 스프레드", "%"),
                        ("VIXCLS", "VIX", ""), ("UNRATE", "실업률", "%"),
                        ("NFCI", "금융여건지수", ""), ("BAMLH0A0HYM2", "HY 스프레드", "%")]
        for i, (key, label, unit) in enumerate(display_keys):
            d = latest.get(key, {})
            cur = d.get("current", 0)
            prev = d.get("prev", cur)
            delta = cur - prev
            delta_str = f"{delta:+.2f}" if delta != 0 else "-"
            with cols[i]:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="label">{label}</div>
                    <div class="value">{cur:.2f}{unit}</div>
                    <div class="sub">{delta_str}</div>
                </div>
                """, unsafe_allow_html=True)

    # Time series charts
    st.markdown("### 시계열 추이")
    c1, c2 = st.columns([3, 1])
    with c1:
        selected_group = st.selectbox("지표 그룹", list(MACRO_GROUPS.keys()))
    with c2:
        period_label = st.selectbox("기간", ["1Y", "3Y", "5Y", "10Y", "ALL"], index=2)
    period_days = {"1Y": 365, "3Y": 1095, "5Y": 1825, "10Y": 3650, "ALL": 9999}[period_label]
    tickers_to_show = MACRO_GROUPS[selected_group]

    with st.spinner(f"{selected_group} 데이터 로딩..."):
        db.prefetch_macro_history(tickers_to_show, days=period_days)
        fig_macro = go.Figure()
        has_data = False
        for t in tickers_to_show:
            hist = db.get_macro_history(t, days=period_days)
            if hist is not None and not hist.empty:
                fig_macro.add_trace(go.Scatter(
                    x=hist.index, y=hist['value'], name=t,
                    line=dict(width=1.5), mode='lines'
                ))
                has_data = True

    if has_data:
        fig_macro.update_layout(
            height=450,
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            font=dict(family=FONT_FAMILY, color="#333"),
            legend=dict(orientation="h", y=1.05, x=0),
            margin=dict(l=0, r=0, t=20, b=0),
            hovermode="x unified",
            xaxis=dict(gridcolor="#f0f0f0"),
            yaxis=dict(gridcolor="#f0f0f0"),
        )
        st.plotly_chart(fig_macro, use_container_width=True)

        # 선택된 그룹의 지표 설명 표시
        with st.expander("📚 선택된 지표 설명", expanded=False):
            for t in tickers_to_show:
                desc = MACRO_DESCRIPTIONS.get(t, "")
                if desc:
                    st.markdown(f"- **{t}**: {desc}")
    else:
        st.warning("Supabase에 해당 지표 데이터가 없습니다. `macro_data_collector.py`를 먼저 실행하세요.")

    # Buffett Indicator
    buffett = db.get_macro_history("BUFFET_INDICATOR", days=period_days)
    if buffett is not None and not buffett.empty:
        st.markdown("### Buffett Indicator")
        st.caption(MACRO_DESCRIPTIONS.get("BUFFET_INDICATOR", ""))
        fig_b = go.Figure()
        fig_b.add_trace(go.Scatter(x=buffett.index, y=buffett['value'], name="Buffett Indicator",
            line=dict(color="#d62728", width=1.5), fill='tozeroy', fillcolor='rgba(214,39,40,0.08)'))
        fig_b.update_layout(
            height=300, plot_bgcolor="#fff", paper_bgcolor="#fff",
            font=dict(family=FONT_FAMILY, color="#333"),
            margin=dict(l=0, r=0, t=10, b=0),
            yaxis=dict(title="S&P500 / GDP × 100", gridcolor="#f0f0f0"),
            xaxis=dict(gridcolor="#f0f0f0"),
        )
        st.plotly_chart(fig_b, use_container_width=True)


# ── Default State ────────────────────────────────────────────────────
if mode == "종목 분석" and not run_analysis:
    st.info("사이드바에서 티커를 입력하고 '분석 실행' 버튼을 클릭하세요.")
elif mode == "종목 비교 (Multi-Screen)" and not run_screening:
    st.info("사이드바에서 종목 리스트를 입력하고 '비교 실행' 버튼을 클릭하세요.")
