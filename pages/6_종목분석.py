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

st.set_page_config(page_title="퀀트 밸류 스크린", layout="wide")

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
st.markdown("# 퀀트 밸류 스크린")
st.markdown("가치 지표(PBR, GP/A, F-Score)를 결합한 퀀트 전략으로 저평가 우량주 50개를 발굴합니다.")


# ── Session State Init ───────────────────────────────────────────────
if "fs_mode" not in st.session_state:
    st.session_state.fs_mode = None

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Mode")
    mode = st.radio(
        "분석 모드 선택",
        ["종목발굴 (스크린)", "개별 종목 분석", "매크로 대시보드"],
        index=0, label_visibility="collapsed"
    )
    st.session_state.fs_mode = mode

    st.markdown("---")

    if mode == "종목발굴 (스크린)":
        st.markdown("### 스크리닝 설정")
        market_choice = st.radio("시장 선택", ["KOSPI 200", "S&P 500", "Mixed (KOR+US)"], index=0)
        run_discovery = st.button("종목 발굴 시작", use_container_width=True)
    else:
        run_discovery = False

    if mode == "개별 종목 분석":
        st.markdown("### 개별 종목 분석")
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

    # Macro mode has no sidebar inputs needed
    run_macro = (mode == "매크로 대시보드")

    st.markdown("---")
    st.caption(f"v3.1 | {datetime.now().strftime('%Y-%m-%d')}")


# ── Analysis Engine Import ───────────────────────────────────────────
from analysis.value_investing import ValueInvestingAnalyzer
from analysis.swing_trading import SwingTradingAnalyzer
from data_collectors.supabase_manager import SupabaseManager

value_analyzer = ValueInvestingAnalyzer()
swing_analyzer = SwingTradingAnalyzer()
db = SupabaseManager()


FONT_FAMILY = "Noto Sans KR, Inter, sans-serif"
CHART_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]


# ── Individual Analysis (개별 종목 분석) ──────────────────────────────
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


# ── Discovery (가치투자 종목발굴) ──────────────────────────────────────
if mode == "종목발굴 (스크린)":
    st.markdown("## 퀀트 가치투자 종목 발굴")
    st.markdown("**전략**: 소형주(하위 20%) + F-Score 7점 이상 + PBR & GP/A 복합 순위 상위 50선")
    
    if run_discovery:
        # 1. 확장된 대상 티커 리스트
        KOSPI_COMPREHENSIVE = [
            "005930.KS", "000660.KS", "035420.KS", "035720.KS", "005380.KS", "000270.KS", "068270.KS", "051910.KS", "006400.KS", "005490.KS",
            "105560.KS", "055550.KS", "032830.KS", "003550.KS", "012330.KS", "015760.KS", "011780.KS", "010950.KS", "034220.KS", "000810.KS",
            "066570.KS", "003670.KS", "030240.KS", "033780.KS", "017670.KS", "009150.KS", "036570.KS", "086790.KS", "004020.KS", "010130.KS",
            "373220.KS", "207940.KS", "000720.KS", "000100.KS", "008930.KS", "012450.KS", "096770.KS", "042700.KS", "011070.KS", "010140.KS",
            "001040.KS", "001450.KS", "002380.KS", "003410.KS", "003490.KS", "004170.KS", "004800.KS", "004990.KS", "005830.KS", "005940.KS",
            "007070.KS", "008770.KS", "009540.KS", "009830.KS", "011170.KS", "011210.KS", "012750.KS", "014680.KS", "016360.KS", "018260.KS",
            "018880.KS", "021240.KS", "024110.KS", "028050.KS", "028260.KS", "028670.KS", "029780.KS", "032640.KS", "034020.KS", "034730.KS",
            "036460.KS", "047040.KS", "047050.KS", "047810.KS", "051900.KS", "069500.KS", "069960.KS", "071050.KS", "078930.KS", "086280.KS",
            "000080.KS", "000210.KS", "000240.KS", "000670.KS", "000720.KS", "000990.KS", "001040.KS", "001230.KS", "001430.KS", "001450.KS",
            "001500.KS", "001740.KS", "001800.KS", "002350.KS", "002380.KS", "002790.KS", "003000.KS", "003090.KS", "003230.KS", "003410.KS",
            "003490.KS", "003520.KS", "003550.KS", "003670.KS", "003850.KS", "004000.KS", "004020.KS", "004170.KS", "004370.KS", "004490.KS"
        ]
        SNP_COMPREHENSIVE = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "BRK-B", "TSLA", "V", "UNH",
            "JNJ", "XOM", "WMT", "MA", "PG", "LLY", "AVGO", "HD", "CVX", "ORCL",
            "ABBV", "KO", "PEP", "MRK", "BAC", "COST", "PFE", "TMO", "MCD", "CSCO",
            "ACN", "ABT", "ADBE", "LIN", "VZ", "DIS", "WFC", "INTC", "TXN", "PM",
            "DHR", "NFLX", "AMD", "RTX", "HON", "NEE", "MS", "AMAT", "LOW", "COP",
            "IBM", "GS", "BA", "GE", "CAT", "UPS", "T", "DE", "LMT", "QCOM",
            "BLK", "INTU", "AXP", "AMGN", "ISRG", "MDLZ", "TJX", "SPGI", "PLD", "SYK",
            "CI", "EL", "GILD", "CB", "ADI", "BDX", "REGN", "ETN", "MMC", "VRTX",
            "LRCX", "BSX", "ZTS", "AMT", "PGR", "MU", "PANW", "SNPS", "FI", "CDNS",
            "NOW", "EQIX", "TGT", "ABNB", "COST", "CRM", "CMG", "DELL", "MAR", "NKE"
        ]
        
        if "KOSPI" in market_choice:
            target_tickers = KOSPI_COMPREHENSIVE
        elif "S&P" in market_choice:
            target_tickers = SNP_COMPREHENSIVE
        else:
            target_tickers = KOSPI_COMPREHENSIVE[:40] + SNP_COMPREHENSIVE[:40]
            
        with st.spinner(f"{len(target_tickers)}개 종목 스크리닝 중... (금융/지주사 제외, PBR & GP/A 분석)"):
            try:
                results = value_analyzer.quant_value_screen(target_tickers)
                
                if results:
                    st.success(f"조건을 만족하는 {len(results)}개 종목을 발견했습니다.")
                    
                    df_q = pd.DataFrame(results).head(50)
                    # 시총 표시 변환
                    df_q['market_cap_str'] = df_q['market_cap'].apply(lambda x: f"${x/1e9:.2f}B" if x > 1e9 else f"${x/1e6:.1f}M")
                    
                    display_cols = ['combined_rank', 'ticker', 'name', 'market_cap_str', 'fscore', 'pbr', 'gpa', 'sector']
                    df_disp = df_q[display_cols].copy()
                    df_disp.columns = ['Rank', 'Ticker', 'Name', 'Market Cap', 'F-Score', 'PBR', 'GP/A', 'Sector']
                    
                    st.dataframe(
                        df_disp.style.format({
                            'PBR': "{:.2f}",
                            'GP/A': "{:.3f}",
                        }).background_gradient(subset=['F-Score'], cmap='Greens')
                          .background_gradient(subset=['PBR'], cmap='RdYlGn_r')
                          .background_gradient(subset=['GP/A'], cmap='RdYlGn'),
                        use_container_width=True, hide_index=True
                    )
                    
                    # ── 상세 분석 연결 ──
                    st.markdown("---")
                    st.markdown("### 상세 분석 바로가기")
                    selected_ticker = st.selectbox("종목 선택", df_q['ticker'].tolist())
                    if st.button("선택 종목 상세 분석"):
                        st.session_state.fs_mode = "개별 종목 분석"
                        # 이 부분은 페이지 리프레시나 상태 변경이 필요함. 
                        # Streamlit 특성상 여기서 직접 '개별 종목 분석'으로 이동시키려면 ticker_input을 세션에 넣고 리런해야 함.
                        st.info(f"사이드바에서 모드를 '개별 종목 분석'으로 변경하고 {selected_ticker}를 입력하세요.")
                else:
                    st.warning("조건(소형주 + F-Score 7점이상)을 만족하는 종목이 현재 리스트에 없습니다.")
                    st.info("KOSPI 200, S&P 500 등 더 넓은 리스트로 확장하거나 필터 조건을 완화해야 합니다.")
            except Exception as e:
                st.error(f"스크리닝 중 오류 발생: {e}")
    else:
        st.info("왼쪽 사이드바에서 '종목 발굴 실행' 버튼을 클릭하세요.")


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
        "BUFFET_INDICATOR_US": "US 버핏 지수 (시가총액 / GDP) — 100% 초과 시 고평가",
        "BUFFET_INDICATOR_KR": "KR 버핏 지수 (시가총액 / GDP 추정) — 한국 시장 저평가 여부",
    }

    # Latest values card row
    with st.spinner("매크로 데이터 로딩 중..."):
        latest = db.get_latest_macro()

    if latest:
        st.markdown("### 주요 지표 현재값")
        cols = st.columns(6)
        display_keys = [("DGS10", "미국 10년 금리", "%"), ("T10Y2Y", "10Y-2Y 스프레드", "%"),
                        ("VIXCLS", "VIX", ""), ("BUFFET_INDICATOR_US", "US 버핏지수", "%"),
                        ("BUFFET_INDICATOR_KR", "KR 버핏지수", "%"), ("BAMLH0A0HYM2", "HY 스프레드", "%")]
        for i, (key, label, unit) in enumerate(display_keys):
            d = latest.get(key, {})
            cur = d.get("current", 0)
            prev = d.get("prev", cur)
            delta = cur - prev
            delta_str = f"{delta:+.2f}" if delta != 0 else "-"
            
            # 버핏지수 색상 반전 (낮을수록 좋음)
            if "BUFFET" in key:
                color = "signal-buy" if cur < 80 else ("signal-sell" if cur > 120 else "signal-hold")
            else:
                color = "" # Default
                
            with cols[i]:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="label">{label}</div>
                    <div class="value {color}">{cur:.1f}{unit}</div>
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
        with st.expander("선택된 지표 설명", expanded=False):
            for t in tickers_to_show:
                desc = MACRO_DESCRIPTIONS.get(t, "")
                if desc:
                    st.markdown(f"- **{t}**: {desc}")
    else:
        st.warning("Supabase에 해당 지표 데이터가 없습니다. `macro_data_collector.py`를 먼저 실행하세요.")

    # Buffett Indicator (US & KR)
    st.markdown("###  Buffett Indicator (Market Temperature)")
    st.info("버핏 인디케이터 = (국가 전체 시가총액 / GDP) × 100. 보통 75~90%가 적정, 115% 이상은 과열로 판단합니다.")
    col_b1, col_b2 = st.columns(2)
    
    with col_b1:
        buff_us = db.get_macro_history("BUFFET_INDICATOR_US", days=period_days)
        if buff_us is not None and not buff_us.empty:
            st.markdown("#### US Buffett Indicator")
            fig_bus = go.Figure()
            fig_bus.add_trace(go.Scatter(x=buff_us.index, y=buff_us['value'], name="US Buffett",
                line=dict(color="#1f77b4", width=1.5), fill='tozeroy', fillcolor='rgba(31,119,180,0.08)'))
            fig_bus.add_hline(y=100, line_dash="dash", line_color="gray", annotation_text="Fair Value")
            fig_bus.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor="#fff", paper_bgcolor="#fff")
            st.plotly_chart(fig_bus, use_container_width=True)
            st.caption("Wilshire 5000 / GDP × 115")

    with col_b2:
        buff_kr = db.get_macro_history("BUFFET_INDICATOR_KR", days=period_days)
        if buff_kr is not None and not buff_kr.empty:
            st.markdown("#### KR Buffett Indicator")
            fig_bkr = go.Figure()
            fig_bkr.add_trace(go.Scatter(x=buff_kr.index, y=buff_kr['value'], name="KR Buffett",
                line=dict(color="#d32f2f", width=1.5), fill='tozeroy', fillcolor='rgba(211,47,47,0.08)'))
            fig_bkr.add_hline(y=100, line_dash="dash", line_color="gray", annotation_text="Fair Value (KOSPI 2500)")
            fig_bkr.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor="#fff", paper_bgcolor="#fff")
            st.plotly_chart(fig_bkr, use_container_width=True)
            st.caption("KOSPI / 2500 × 100")


# ── Default State ────────────────────────────────────────────────────
if mode == "개별 종목 분석" and not run_analysis:
    st.info("사이드바에서 티커를 입력하고 '분석 실행' 버튼을 클릭하세요.")
elif mode == "종목발굴 (스크린)" and not run_discovery:
    st.info("왼쪽 사이드바에서 '종목 발굴 시작' 버튼을 클릭하세요.")
