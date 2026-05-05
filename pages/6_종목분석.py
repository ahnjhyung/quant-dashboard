"""
통합 퀀트 종목 분석 대시보드 (Premium Edition)
=======================================================
개별 종목 분석: 가치투자(DCF, F-Score) + 기술적 분석(RSI, MACD, 볼린저밴드)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time

# --- Page Config ---
st.set_page_config(
    page_title="종목 분석 | 통합 퀀트 시스템",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Premium CSS (Pure White Professional Theme) ---
st.markdown("""
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");

:root {
    --primary: #4f46e5;
    --primary-dark: #3730a3;
    --secondary: #db2777;
    --success: #059669;
    --danger: #dc2626;
    --warning: #d97706;
    --background: #ffffff;
    --card-bg: #ffffff;
    --sidebar-bg: #ffffff;
    --glass-border: rgba(0, 0, 0, 0.08);
    --text-main: #1e293b;
    --text-muted: #64748b;
    --chart-grid: rgba(0, 0, 0, 0.05);
}

* { font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', 'Segoe UI', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif; }

[data-testid="stAppViewContainer"] {
    background-color: var(--background);
    color: var(--text-main);
}

[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] {
    background-color: var(--sidebar-bg);
    border-right: 1px solid var(--glass-border);
}

.glass-card {
    background: var(--card-bg);
    border-radius: 12px;
    border: 1px solid var(--glass-border);
    padding: 24px;
    margin-bottom: 24px;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
    transition: all 0.2s ease;
    overflow: hidden;
}
.glass-card:hover {
    border-color: var(--primary);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
}

.metric-box { text-align: center; padding: 15px; }
.metric-label {
    font-size: 0.85rem;
    color: var(--text-muted);
    font-weight: 600;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.metric-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--text-main);
    line-height: 1.2;
}
.metric-delta { font-size: 0.9rem; margin-top: 6px; font-weight: 500; }

.verdict-container {
    padding: 40px;
    border-radius: 16px;
    text-align: center;
    margin-bottom: 30px;
    color: white;
}
.verdict-buy { background: linear-gradient(135deg, #10b981, #059669); }
.verdict-hold { background: linear-gradient(135deg, #f59e0b, #d97706); }
.verdict-sell { background: linear-gradient(135deg, #ef4444, #dc2626); }

.verdict-title { font-size: 2.8rem; font-weight: 800; margin: 0; color: white; letter-spacing: -1px; }
.verdict-score { font-size: 1.2rem; opacity: 0.9; margin-top: 12px; color: white; font-weight: 500; }

.progress-bg { background: #f1f5f9; border-radius: 10px; height: 10px; width: 100%; margin-top: 15px; }
.progress-fill { height: 100%; border-radius: 10px; transition: width 0.8s ease-out; }

.stTabs [data-baseweb="tab-list"] { gap: 32px; border-bottom: 1px solid var(--glass-border); }
.stTabs [data-baseweb="tab"] {
    color: var(--text-muted) !important;
    font-weight: 600 !important;
    padding: 12px 0 !important;
    font-size: 1rem !important;
}
.stTabs [aria-selected="true"] {
    color: var(--primary) !important;
    border-bottom: 2px solid var(--primary) !important;
}

/* Fix for potential cropping in Streamlit columns */
[data-testid="column"] {
    padding: 0 10px !important;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
.animate-fade { animation: fadeIn 0.5s ease-out forwards; }
</style>
""", unsafe_allow_html=True)

# --- Analysis Engine Import ---
from analysis.value_investing import ValueInvestingAnalyzer
from analysis.swing_trading import SwingTradingAnalyzer
from data_collectors.supabase_manager import SupabaseManager

value_analyzer = ValueInvestingAnalyzer()
swing_analyzer = SwingTradingAnalyzer()
db = SupabaseManager()

# --- Sidebar Configuration ---
with st.sidebar:
    st.markdown("<h2 style='margin-top:0; color:#1e293b; font-weight:700;'>종목 분석</h2>", unsafe_allow_html=True)
    
    st.markdown("### 분석 모드 선택")
    mode = st.radio("메뉴", ["마이크로 분석", "매크로 분석"], index=0, label_visibility="collapsed")
    
    st.markdown("---")
    
    if mode == "마이크로 분석":
        ticker_input = st.text_input("종목 코드 (Ticker)", value="NVDA", help="예: TSLA, AAPL, 005930.KS")
        period = st.selectbox("데이터 분석 범위", ["6개월", "1년", "2년", "5년"], index=1)
        period_map = {"6개월": "6mo", "1년": "1y", "2년": "2y", "5년": "5y"}
        selected_period = period_map[period]
        run_btn = st.button("데이터 분석 시작", use_container_width=True, type="primary")
    else:
        run_btn = False
        ticker_input = ""

    st.markdown("---")
    st.caption("Alpha Generation System v4.5 Premium")

# --- Main Dashboard Logic ---
if mode == "마이크로 분석":
    if not ticker_input:
        st.info("분석할 종목 코드를 입력하고 '데이터 분석 시작' 버튼을 클릭해 주세요.")
    else:
        if run_btn:
            raw_ticker = ticker_input.strip().upper()
            
            # 한국 종목 자동 보정 (6자리 숫자일 경우)
            if raw_ticker.isdigit() and len(raw_ticker) == 6:
                # 기본적으로 KOSPI(.KS) 시도 후 데이터 없으면 KOSDAQ(.KQ) 시도
                ticker = f"{raw_ticker}.KS"
                with st.spinner(f"코스피 데이터 확인 중: {ticker}..."):
                    test_df = swing_analyzer.get_ohlcv(ticker, period="1mo")
                    if test_df.empty:
                        ticker = f"{raw_ticker}.KQ"
                        st.caption(f"코스피 데이터가 없어 코스닥({ticker})으로 전환합니다.")
            else:
                ticker = raw_ticker

            with st.spinner(f"금융 데이터 수집 및 알고리즘 분석 진행 중: {ticker}..."):
                try:
                    fscore_data = value_analyzer.piotroski_score(ticker)
                    dcf_data = value_analyzer.dcf_valuation(ticker)
                    full_val = value_analyzer.full_value_analysis(ticker)
                    swing_data = swing_analyzer.full_analysis(ticker, period=selected_period)
                    
                    st.session_state['ticker'] = ticker
                    st.session_state['fscore_data'] = fscore_data
                    st.session_state['dcf_data'] = dcf_data
                    st.session_state['full_val'] = full_val
                    st.session_state['swing_data'] = swing_data
                except Exception as e:
                    st.error(f"분석 중 오류가 발생했습니다: {str(e)}")

        if 'ticker' in st.session_state and st.session_state['ticker'] == ticker_input.strip().upper():
            ticker = st.session_state['ticker']
            fscore_data = st.session_state['fscore_data']
            dcf_data = st.session_state['dcf_data']
            full_val = st.session_state['full_val']
            swing_data = st.session_state['swing_data']

            if "error" in swing_data:
                st.error(f"{ticker} 종목의 데이터를 찾을 수 없습니다. 심볼이 올바른지 확인해 주세요.")
            else:
                # 1. TOP VERDICT SECTION
                current_price = swing_data.get('current_price', 0)
                signal = swing_data.get('swing_signal', 'HOLD')
                confidence = swing_data.get('confidence', 0)
                fscore = fscore_data.get('score', 0)
                upside = full_val.get('upside_pct', 0)
                
                tech_rm = swing_data.get('risk_management', {})
                tech_ev = tech_rm.get('expected_value_pct', 0) * 100 
                fund_ev = full_val.get('expected_value_pct', 0)
                
                hybrid_ev = (tech_ev * 0.5) + (fund_ev * 0.5)
                
                f_norm = fscore / 9
                d_norm = min(max((upside + 20) / 100, 0), 1)
                t_norm = confidence if "BUY" in signal else (1 - confidence if "SELL" in signal else 0.5)
                
                hybrid_score = (f_norm * 0.4 + d_norm * 0.3 + t_norm * 0.3) * 100
                
                if hybrid_score >= 70:
                    v_class, v_text, v_sub = "verdict-buy", "적극 매수 (Strong Buy)", "기본적 가치와 시장 모멘텀이 모두 우상향하고 있습니다."
                elif hybrid_score >= 45:
                    v_class, v_text, v_sub = "verdict-hold", "매수 관점 (Accumulate)", "단기 기술적 반등 또는 중장기 매집이 유효한 구간입니다."
                else:
                    v_class, v_text, v_sub = "verdict-sell", "관망/매도 권고 (Avoid)", "고평가 부담 또는 추세 하락 전환 위험이 감지되었습니다."

                st.markdown(f"""
                <div class="verdict-container {v_class} animate-fade">
                    <p style='color:rgba(255,255,255,0.9); margin:0; text-transform:uppercase; font-weight:600; letter-spacing:2px;'>{ticker} 종합 투자 판단 결과</p>
                    <h1 class="verdict-title">{v_text}</h1>
                    <p class="verdict-score">인공지능 종합 평가 점수: {hybrid_score:.1f}% | {v_sub}</p>
                </div>
                """, unsafe_allow_html=True)

                # 2. KEY METRICS GRID
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                
                currency_symbol = "₩" if ticker.endswith((".KS", ".KQ")) else "$"
                
                with m_col1:
                    st.markdown(f"""
                    <div class="glass-card metric-box animate-fade">
                        <div class="metric-label">현재 주가</div>
                        <div class="metric-value">{currency_symbol}{current_price:,.0f if currency_symbol == "₩" else ",.2f"}</div>
                        <div class="metric-delta" style='color:var(--text-muted)'>실시간 시세 데이터</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with m_col2:
                    ev_color = "var(--success)" if hybrid_ev > 0 else "var(--danger)"
                    st.markdown(f"""
                    <div class="glass-card metric-box animate-fade">
                        <div class="metric-label">통합 기대 수익률 (EV)</div>
                        <div class="metric-value" style='color:{ev_color}'>{hybrid_ev:+.2f}%</div>
                        <div class="metric-delta" style='color:var(--text-muted)'>수치 기반 알고리즘 예측</div>
                    </div>
                    """, unsafe_allow_html=True)

                with m_col3:
                    f_color = "var(--success)" if fscore >= 7 else ("var(--warning)" if fscore >= 4 else "var(--danger)")
                    st.markdown(f"""
                    <div class="glass-card metric-box animate-fade">
                        <div class="metric-label">재무 건전성 점수</div>
                        <div class="metric-value" style='color:{f_color}'>{fscore}/9</div>
                        <div class="progress-bg"><div class="progress-fill" style="width:{fscore/9*100}%; background:{f_color}"></div></div>
                    </div>
                    """, unsafe_allow_html=True)

                with m_col4:
                    sig_color = "var(--success)" if "BUY" in signal else ("var(--danger)" if "SELL" in signal else "var(--warning)")
                    kor_signal = "매수" if "BUY" in signal else ("매도" if "SELL" in signal else "중립")
                    st.markdown(f"""
                    <div class="glass-card metric-box animate-fade">
                        <div class="metric-label">기술적 매매 신호</div>
                        <div class="metric-value" style='color:{sig_color}'>{kor_signal}</div>
                        <div class="metric-delta" style='color:var(--text-muted)'>알고리즘 신뢰도: {confidence*100:.0f}%</div>
                    </div>
                    """, unsafe_allow_html=True)

                # 3. DETAILED ANALYSIS TABS
                tab1, tab2, tab3 = st.tabs(["투자 전략 요약", "기본적 분석 (펀더멘털)", "기술적 분석 (모멘텀)"])
                
                with tab1:
                    col_left, col_right = st.columns([2, 1])
                    with col_left:
                        st.markdown("### 주가 차트 및 지표 분석")
                        ohlcv = swing_data.get('ohlcv', pd.DataFrame())
                        if not ohlcv.empty:
                            fig = make_subplots(
                                rows=2, cols=1, shared_xaxes=True,
                                vertical_spacing=0.05, row_heights=[0.7, 0.3]
                            )
                            fig.add_trace(go.Candlestick(x=ohlcv.index, open=ohlcv['Open'], high=ohlcv['High'], low=ohlcv['Low'], close=ohlcv['Close'], name="주가"), row=1, col=1)
                            
                            upper, mid, lower, _, _ = swing_analyzer.bollinger_bands(ohlcv['Close'])
                            fig.add_trace(go.Scatter(x=ohlcv.index, y=upper, line=dict(color='rgba(79, 70, 229, 0.3)', width=1), name="볼린저 상단"), row=1, col=1)
                            fig.add_trace(go.Scatter(x=ohlcv.index, y=lower, line=dict(color='rgba(79, 70, 229, 0.3)', width=1), fill='tonexty', fillcolor='rgba(79, 70, 229, 0.05)', name="볼린저 하단"), row=1, col=1)
                            
                            fig.add_trace(go.Bar(x=ohlcv.index, y=ohlcv['Volume'], name="거래량", marker_color="rgba(148, 163, 184, 0.5)"), row=2, col=1)
                            
                            fig.update_layout(
                                height=550, template="plotly_white",
                                xaxis_rangeslider_visible=False,
                                margin=dict(l=60, r=40, t=50, b=50),
                                hovermode='x unified'
                            )
                            fig.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.05)')
                            fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.05)')
                            st.plotly_chart(fig, use_container_width=True)

                    with col_right:
                        st.markdown("### 핵심 투자 가설 및 근거")
                        st.markdown(f"""
                        <div class="glass-card">
                            <h4 style='margin-top:0; color:var(--primary); font-size:1.1rem;'>전략적 투자 포인트</h4>
                            <p style='font-size:0.95rem; line-height:1.7; color:var(--text-main);'>
                                <b>{ticker}</b> 종목은 현재 데이터 분석 결과 <b>{v_text}</b> 단계에 해당합니다.
                                <br><br>
                                <b>펀더멘털:</b> 피오트로스키 평가 기준 <b>{fscore_data['category']}</b> 상태입니다. 
                                {'현저한 저평가' if upside > 20 else '안전 마진 확보' if upside > 5 else '적정 가치 도달'} 구간으로 판단되며, 
                                모델 산출 기대 수익률은 약 <b>{upside:+.1f}%</b>입니다.
                                <br><br>
                                <b>모멘텀:</b> 기술적 지표를 종합한 결과 <b>{kor_signal}</b> 신호가 감지되었습니다. 
                                현재 RSI 수치는 <b>{swing_data['rsi']['value']:.1f}</b>로 {swing_data['rsi']['signal']} 권역에 위치해 있습니다.
                            </p>
                            <hr style='border-color:var(--glass-border); margin:20px 0;'>
                            <p style='font-size:0.8rem; text-transform:uppercase; letter-spacing:1px; color:var(--text-muted); font-weight:700;'>에이전트별 통합 기대 수익률 (EV)</p>
                            <div style='display:flex; justify-content:space-between; margin-bottom:12px;'>
                                <span>펀더멘털 에이전트</span>
                                <span style='color:{"var(--success)" if fund_ev > 0 else "var(--danger)"}; font-weight:600;'>{fund_ev:+.2f}%</span>
                            </div>
                            <div style='display:flex; justify-content:space-between; margin-bottom:12px;'>
                                <span>모멘텀 에이전트</span>
                                <span style='color:{"var(--success)" if tech_ev > 0 else "var(--danger)"}; font-weight:600;'>{tech_ev:+.2f}%</span>
                            </div>
                            <div style='display:flex; justify-content:space-between; font-weight:800; border-top:2px solid var(--glass-border); padding-top:15px; margin-top:10px;'>
                                <span style='color:var(--primary);'>종합 판단 합계</span>
                                <span style='color:var(--primary); font-size:1.15rem;'>{hybrid_ev:+.2f}%</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.markdown("#### 기대값 계산 수식")
                        st.latex(r"EV_{Hybrid} = \frac{EV_{Value} + EV_{Tech}}{2}")
                        st.latex(r"EV = (P_{win} \times \text{Avg Profit}) - (P_{loss} \times \text{Avg Loss})")

                with tab2:
                    st.markdown("### 기본적 분석 상세 (가치 평가)")
                    f_col1, f_col2 = st.columns(2)
                    with f_col1:
                        st.markdown("#### 내재 가치 추정 (현금흐름 할인법)")
                        if "error" not in dcf_data:
                            st.markdown(f"""
                            <div class="glass-card">
                                <div style='display:flex; justify-content:space-between; margin-bottom:20px;'>
                                    <span style='color:var(--text-muted)'>모델 산출 적정 주가</span>
                                    <span style='font-size:1.7rem; font-weight:700; color:var(--primary);'>${dcf_data.get('intrinsic_value_per_share', 0):,.2f}</span>
                                </div>
                                <div style='display:flex; justify-content:space-between; margin-bottom:15px;'>
                                    <span style='color:var(--text-muted)'>안전 마진 (Margin of Safety)</span>
                                    <span style='color:var(--success); font-weight:600;'>{dcf_data.get('margin_of_safety', 0)*100:.1f}%</span>
                                </div>
                                <div style='display:flex; justify-content:space-between;'>
                                    <span style='color:var(--text-muted)'>영구 성장률 (Terminal Growth)</span>
                                    <span style='font-weight:500;'>{dcf_data.get('parameters', {}).get('terminal_growth', 0)*100:.1f}%</span>
                                </div>
                                <hr style='border-color:var(--glass-border);'>
                                <p style='font-size:0.85rem; color:var(--text-muted); line-height:1.5;'>* 10개년 잉여현금흐름(FCF) 추정치 및 가중평균자본비용(WACC) 할인 모델을 적용한 결과입니다.</p>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.warning("분석에 필요한 충분한 재무 데이터를 확보하지 못했습니다.")
                    
                    with f_col2:
                        st.markdown("#### 재무 건전성 상세 평가 (Piotroski)")
                        details = fscore_data.get('details', {})
                        if details:
                            translation_map = {
                                "F1_ROA": "수익성: 당기순이익 발생 (ROA > 0)",
                                "F2_CFO": "현금흐름: 영업활동 현금흐름 (+)",
                                "F3_Delta_ROA": "성장성: ROA 전년 대비 개선",
                                "F4_Accrual": "회계 품질: 영업현금흐름 > 순이익",
                                "F5_Delta_Leverage": "재무 구조: 부채비율 전년 대비 감소",
                                "F6_Delta_Liquidity": "유동성: 유동비율 전년 대비 개선",
                                "F7_EQ_Issue": "자본: 신주 발행 없음 (주식 희석 방지)",
                                "F8_Delta_Margin": "효율성: 매출총이익률 전년 대비 개선",
                                "F9_Delta_Turnover": "회전율: 총자산회전율 전년 대비 개선"
                            }
                            f_items = []
                            for k, v in details.items():
                                label = translation_map.get(k, k)
                                f_items.append({"평가 항목": label, "결과": "적합" if v else "부적합"})
                            
                            f_df = pd.DataFrame(f_items)
                            st.dataframe(f_df, hide_index=True, use_container_width=True)

                with tab3:
                    st.markdown("### 기술적 분석 상세 (트레이딩 전략)")
                    t_col1, t_col2 = st.columns(2)
                    with t_col1:
                        st.markdown("#### 보조지표별 매수/매도 신호")
                        t_sigs = swing_data.get('signals', {})
                        for name, info in t_sigs.items():
                            color = "var(--success)" if "BUY" in info['signal'] else ("var(--danger)" if "SELL" in info['signal'] else "var(--warning)")
                            kor_sig = "매수" if "BUY" in info['signal'] else ("매도" if "SELL" in info['signal'] else "중립")
                            st.markdown(f"""
                            <div style='padding:20px; border-left:5px solid {color}; background:#ffffff; border-radius:12px; margin-bottom:15px; border:1px solid var(--glass-border);'>
                                <div style='display:flex; justify-content:space-between; align-items:center;'>
                                    <b style='color:var(--text-main); font-size:1.05rem;'>{name}</b>
                                    <span style='color:{color}; font-weight:700; font-size:0.85rem; padding:4px 10px; background:white; border-radius:20px; border:1px solid {color}55;'>{kor_sig}</span>
                                </div>
                                <p style='margin:12px 0 0 0; font-size:0.92rem; color:var(--text-muted); line-height:1.5;'>{info['reason']}</p>
                            </div>
                            """, unsafe_allow_html=True)
                    
                with t_col2:
                        st.markdown("#### 추세 판단 및 리스크 관리 전략")
                        cross = swing_data.get('ma_cross', {})
                        rm = swing_data.get('risk_management', {})
                        
                        trend_label = "상승 추세" if "UP" in cross.get('trend_status', '') else ("하락 추세" if "DOWN" in cross.get('trend_status', '') else "횡보 구간")
                        st.markdown(f"""
                        <div class="glass-card">
                            <p style='margin-bottom:15px;'><b>현재 주가 추세:</b> <span style='color:var(--primary); font-weight:600;'>{trend_label}</span></p>
                            <p style='margin-bottom:15px;'><b>200일 지수이동평균 (EMA):</b> {currency_symbol}{cross.get('ema200', 0):,.0f if currency_symbol == "₩" else ",.2f"} ({'주가 상회' if cross.get('price_above_ema200') else '주가 하회'})</p>
                            <p style='margin-bottom:15px;'><b>변동성 지표 (ATR):</b> {currency_symbol}{swing_data.get('atr', 0):,.0f if currency_symbol == "₩" else ",.2f"}</p>
                            <hr style='border-color:var(--glass-border); margin:20px 0;'>
                            <p style='color:var(--primary); font-weight:700; margin-bottom:18px;'>포지션 진입 및 청산 가이드</p>
                            <div style='display:grid; grid-template-columns: 1fr 1fr; gap:24px;'>
                                <div><small style='color:var(--text-muted); font-weight:600;'>진입 권장가</small><br><b style='font-size:1.15rem;'>{currency_symbol}{rm.get('target', 0):,.0f if currency_symbol == "₩" else ",.2f"}</b></div>
                                <div><small style='color:var(--text-muted); font-weight:600;'>리스크 손절가</small><br><b style='font-size:1.15rem; color:var(--danger);'>{currency_symbol}{rm.get('stop_loss', 0):,.0f if currency_symbol == "₩" else ",.2f"}</b></div>
                                <div><small style='color:var(--text-muted); font-weight:600;'>손익비 (R/R)</small><br><b style='font-size:1.15rem;'>1 : {rm.get('risk_reward_ratio', 0):.1f}</b></div>
                                <div><small style='color:var(--text-muted); font-weight:600;'>알고리즘 예상 승률</small><br><b style='font-size:1.15rem;'>{rm.get('win_probability', 0)*100:.1f}%</b></div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

elif mode == "매크로 분석":
    st.markdown("<h2 class='animate-fade' style='color:#1e293b; font-weight:700;'>매크로 경제 데이터 분석</h2>", unsafe_allow_html=True)
    
    with st.spinner("거시경제 실시간 데이터 동기화 중..."):
        latest = db.get_latest_macro()
        
    if latest:
        # 상단 핵심 지표 요약
        cols = st.columns(4)
        top_metrics = [
            ("NET_LIQUIDITY", "미국 실질 순유동성", "B", "Fed 자산 - TGA - RRP. 시장의 가용 달러 규모."),
            ("DEXKOUS", "원/달러 환율", "₩", "달러 대비 원화 가치. 외국인 수급의 핵심 지표."),
            ("VIXCLS", "VIX 공포지수", "", "S&P 500 변동성 기대치. 20 이상 시 위험 회피 심리 강화."),
            ("T10Y2Y", "장단기 금리차", "%", "10년물 - 2년물 금리. 마이너스(역전) 시 경기 침체 전조.")
        ]
        
        for i, (key, label, unit, desc) in enumerate(top_metrics):
            d = latest.get(key, {})
            val = d.get("current", 0)
            delta = val - d.get("prev", val)
            with cols[i]:
                st.markdown(f"""
                <div class="glass-card metric-box animate-fade" title="{desc}">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value" style='font-size:1.4rem;'>{val:,.2f}{unit}</div>
                    <div class="metric-delta" style='color:{"#10b981" if delta <=0 else "#ef4444"}; font-weight:600;'>{delta:+.2f}</div>
                </div>
                """, unsafe_allow_html=True)

        # 상세 유동성 지표 (TGA, RRP 등)
        st.markdown("#### 유동성 세부 지표")
        cols_liq = st.columns(3)
        liq_metrics = [
            ("WALCL_B", "연준 총자산 (Fed Assets)", "B", "연준이 보유한 채권 및 자산 규모 (양적완화/긴축)"),
            ("TGA_B", "재무부 일반계정 (TGA)", "B", "정부의 현금 잔고. 지출 시 시장 유동성 증가."),
            ("RRP_B", "역레포 잔고 (RRP)", "B", "시중의 유휴 자금. 감소 시 시장 유동성 공급 효과.")
        ]
        for i, (key, label, unit, desc) in enumerate(liq_metrics):
            d = latest.get(key, {})
            val = d.get("current", 0)
            delta = val - d.get("prev", val)
            with cols_liq[i]:
                st.markdown(f"""
                <div class="glass-card metric-box animate-fade" style='padding:15px;' title="{desc}">
                    <div class="metric-label" style='font-size:0.75rem;'>{label}</div>
                    <div class="metric-value" style='font-size:1.1rem;'>{val:,.2f}{unit}</div>
                    <div class="metric-delta" style='font-size:0.8rem; color:{"#10b981" if delta <=0 else "#ef4444"};'>{delta:+.2f}</div>
                </div>
                """, unsafe_allow_html=True)

    # --- Historical Trend Analysis Section ---
    st.markdown("<hr style='border-color:var(--glass-border); margin:40px 0;'>", unsafe_allow_html=True)
    st.markdown("### 역사적 거시지표 추세 및 상세 분석")
    st.caption("지표별 업데이트 주기(Daily, Weekly, Monthly)에 따라 분류하여 시장의 흐름을 다각도로 분석합니다.")
    
    TICKER_LABELS = {
        "WALCL_B": "연준 총자산(Billions)", "TGA_B": "재무부 현금잔고(TGA)", "RRP_B": "역레포(RRP)", "NET_LIQUIDITY": "실질 순유동성",
        "DGS2": "미 2년물 국채금리", "DGS10": "미 10년물 국채금리", "T10Y2Y": "장단기 금리차(10Y-2Y)", "T10Y3M": "금리차(10Y-3M)",
        "CPIAUCSL": "미국 소비자물가지수(CPI)", "VIXCLS": "변동성 지수(VIX)", "BAMLH0A0HYM2": "하이일드 스프레드",
        "DEXKOUS": "원/달러 환율", "ICSA": "신규 실업수당 청구건수", "UNRATE": "미국 실업률"
    }

    TICKER_DESCS = {
        "NET_LIQUIDITY": "<b>실질 순유동성:</b> 연준의 총자산에서 정부 잔고와 역레포를 뺀 수치로, 실제 시장에 풀린 달러 유동성을 의미합니다. 주가와 높은 상관관계를 보입니다.",
        "T10Y2Y": "<b>장단기 금리차:</b> 경기 침체의 가장 강력한 선행 지표입니다. 마이너스(역전) 후 다시 플러스로 돌아올 때(Uninversion) 역사적으로 침체가 발생했습니다.",
        "VIXCLS": "<b>VIX (공포지수):</b> 시장의 불안 수준을 나타냅니다. 30 이상은 극도의 공포(매수 기회), 15 미만은 과도한 낙관(조정 주의)을 시사합니다.",
        "WALCL_B": "<b>연준 총자산:</b> 양적완화(QE)나 긴축(QT)의 척도입니다. 자산이 늘어나면 유동성이 공급되어 자산 가격에 우호적입니다.",
        "TGA_B": "<b>TGA (정부 잔고):</b> 재무부가 보유한 현금입니다. 정부가 돈을 쓰면 TGA가 줄어들고 시중 유동성은 늘어납니다.",
        "ICSA": "<b>주간 실업수당 청구:</b> 고용 시장의 실시간 건전성을 보여주는 주간 지표입니다. 추세적 상승 시 경기 둔화 신호로 해석합니다."
    }

    macro_tabs = st.tabs(["Market (Daily)", "Weekly (Liquidity/Jobs)", "Monthly (Economy/Inflation)"])
    
    with macro_tabs[0]:
        st.markdown("#### 실시간 시장 지표 (Daily)")
        st.info("매일 변동하는 금리, 환율, 변동성 지표입니다. 단기적인 시장 심리와 수급을 파악하는 데 유용합니다.")
        daily_tickers = ["DGS10", "DGS2", "T10Y2Y", "VIXCLS", "DEXKOUS"]
        
        for t in daily_tickers:
            h = db.get_macro_history(t, days=1000)
            if h is not None and not h.empty:
                with st.expander(f"{TICKER_LABELS.get(t, t)} 상세보기", expanded=(t=="T10Y2Y")):
                    st.markdown(TICKER_DESCS.get(t, ""), unsafe_allow_html=True)
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=h.index, y=h['value'], name=TICKER_LABELS.get(t, t), line=dict(color="#4f46e5", width=2)))
                    fig.update_layout(height=300, margin=dict(l=40, r=40, t=20, b=40), template="plotly_white")
                    st.plotly_chart(fig, use_container_width=True)

    with macro_tabs[1]:
        st.markdown("#### 주간 유동성 및 고용 지표 (Weekly)")
        st.info("매주 발표되는 연준의 자산 현황과 고용 지표입니다. 중기적인 유동성 환경을 진단합니다.")
        weekly_tickers = ["NET_LIQUIDITY", "WALCL_B", "TGA_B", "RRP_B", "ICSA"]
        
        for t in weekly_tickers:
            h = db.get_macro_history(t, days=1500)
            if h is not None and not h.empty:
                with st.expander(f"{TICKER_LABELS.get(t, t)} 상세보기", expanded=(t=="NET_LIQUIDITY")):
                    st.markdown(TICKER_DESCS.get(t, ""), unsafe_allow_html=True)
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=h.index, y=h['value'], name=TICKER_LABELS.get(t, t), line=dict(color="#10b981", width=2)))
                    fig.update_layout(height=300, margin=dict(l=40, r=40, t=20, b=40), template="plotly_white")
                    st.plotly_chart(fig, use_container_width=True)

    with macro_tabs[2]:
        st.markdown("#### 월간 경제 및 물가 지표 (Monthly)")
        st.info("국가의 펀더멘털을 결정하는 핵심 지표입니다. 장기적인 경기 방향성을 결정합니다.")
        monthly_tickers = ["CPIAUCSL", "UNRATE", "BAMLH0A0HYM2"]
        
        for t in monthly_tickers:
            h = db.get_macro_history(t, days=2500)
            if h is not None and not h.empty:
                with st.expander(f"{TICKER_LABELS.get(t, t)} 상세보기", expanded=(t=="CPIAUCSL")):
                    st.markdown(TICKER_DESCS.get(t, ""), unsafe_allow_html=True)
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=h.index, y=h['value'], name=TICKER_LABELS.get(t, t), line=dict(color="#ef4444", width=2)))
                    fig.update_layout(height=300, margin=dict(l=40, r=40, t=20, b=40), template="plotly_white")
                    st.plotly_chart(fig, use_container_width=True)

# --- Footer ---
st.markdown("---")
st.markdown("<p style='text-align:center; color:var(--text-muted); font-size:0.85rem; font-weight:500;'>종목 분석 대시보드 v4.5 Premium | 데이터 기반 무결성 및 기대값 투자 시스템</p>", unsafe_allow_html=True)
