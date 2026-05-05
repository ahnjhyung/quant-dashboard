"""
Fundamental & Swing Analysis Dashboard (Premium Edition)
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
    page_title="Stock Intelligence Pro",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Premium CSS (Glassmorphism & Vibrant UI) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap');

:root {
    --primary: #6366f1;
    --primary-dark: #4f46e5;
    --secondary: #ec4899;
    --success: #10b981;
    --danger: #ef4444;
    --warning: #f59e0b;
    --background: #0f172a;
    --glass: rgba(255, 255, 255, 0.03);
    --glass-border: rgba(255, 255, 255, 0.1);
    --text-main: #f8fafc;
    --text-muted: #94a3b8;
}

* { font-family: 'Outfit', 'Noto Sans KR', sans-serif; }

/* Global Styling */
[data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at top right, #1e293b, #0f172a);
    color: var(--text-main);
}

[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] {
    background-color: rgba(15, 23, 42, 0.95);
    border-right: 1px solid var(--glass-border);
}

/* Glassmorphism Cards */
.glass-card {
    background: var(--glass);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-radius: 20px;
    border: 1px solid var(--glass-border);
    padding: 24px;
    margin-bottom: 24px;
    transition: all 0.3s ease;
}
.glass-card:hover {
    border-color: rgba(99, 102, 241, 0.4);
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
}

.metric-box {
    text-align: center;
    padding: 15px;
}
.metric-label {
    font-size: 0.8rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 8px;
}
.metric-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--text-main);
}
.metric-delta {
    font-size: 0.9rem;
    margin-top: 4px;
}

/* Verdict Styles */
.verdict-container {
    padding: 30px;
    border-radius: 24px;
    text-align: center;
    margin-bottom: 30px;
    position: relative;
    overflow: hidden;
}
.verdict-container::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: linear-gradient(45deg, rgba(255,255,255,0.1), transparent);
    z-index: 1;
}
.verdict-buy { background: linear-gradient(135deg, #065f46, #10b981); box-shadow: 0 10px 40px -10px rgba(16, 185, 129, 0.5); }
.verdict-hold { background: linear-gradient(135deg, #92400e, #f59e0b); box-shadow: 0 10px 40px -10px rgba(245, 158, 11, 0.5); }
.verdict-sell { background: linear-gradient(135deg, #991b1b, #ef4444); box-shadow: 0 10px 40px -10px rgba(239, 68, 68, 0.5); }

.verdict-title { font-size: 2.5rem; font-weight: 800; margin: 0; z-index: 2; position: relative; color: white; }
.verdict-score { font-size: 1.1rem; opacity: 0.9; margin-top: 5px; z-index: 2; position: relative; color: white; }

/* Custom Progress Bar */
.progress-bg { background: rgba(255,255,255,0.1); border-radius: 10px; height: 8px; width: 100%; margin-top: 10px; }
.progress-fill { height: 100%; border-radius: 10px; transition: width 1s ease-in-out; }

/* Tabs Styling */
.stTabs [data-baseweb="tab-list"] { gap: 24px; background-color: transparent; }
.stTabs [data-baseweb="tab"] {
    height: 50px;
    background-color: transparent !important;
    border: none !important;
    color: var(--text-muted) !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
}
.stTabs [aria-selected="true"] {
    color: var(--primary) !important;
    border-bottom: 3px solid var(--primary) !important;
}

/* Animations */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
.animate-fade { animation: fadeIn 0.6s ease-out forwards; }
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
    st.image("https://img.icons8.com/fluency/96/diamond.png", width=60)
    st.markdown("<h2 style='margin-top:0;'>Quant Intelligence</h2>", unsafe_allow_html=True)
    
    st.markdown("### Analysis Suite")
    mode = st.radio("Select View", ["Single Stock Analysis", "Macro Liquidity"], index=0)
    
    st.markdown("---")
    
    if mode == "Single Stock Analysis":
        ticker_input = st.text_input("Ticker Symbol", value="NVDA", help="e.g., TSLA, AAPL, 005930.KS")
        period = st.selectbox("Historical Lookback", ["6mo", "1y", "2y", "5y"], index=1)
        run_btn = st.button("RUN DEEP ANALYSIS", use_container_width=True, type="primary")
    else:
        run_btn = False
        ticker_input = ""

    st.markdown("---")
    st.caption("Engineered for Alpha")

# --- Main Dashboard Logic ---

if mode == "Single Stock Analysis":
    if not ticker_input:
        st.info("💡 Enter a ticker symbol in the sidebar to begin analysis.")
    else:
        # Use session state to persist analysis results across tab changes
        if run_btn:
            ticker = ticker_input.strip().upper()
            
            with st.spinner(f"🚀 Initializing AI-Driven Hybrid Analysis for {ticker}..."):
                # Fetch Data
                fscore_data = value_analyzer.piotroski_score(ticker)
                dcf_data = value_analyzer.dcf_valuation(ticker)
                full_val = value_analyzer.full_value_analysis(ticker)
                swing_data = swing_analyzer.full_analysis(ticker, period=period)
                
                # Store in session state
                st.session_state['ticker'] = ticker
                st.session_state['fscore_data'] = fscore_data
                st.session_state['dcf_data'] = dcf_data
                st.session_state['full_val'] = full_val
                st.session_state['swing_data'] = swing_data

        if 'ticker' in st.session_state and st.session_state['ticker'] == ticker_input.strip().upper():
            ticker = st.session_state['ticker']
            fscore_data = st.session_state['fscore_data']
            dcf_data = st.session_state['dcf_data']
            full_val = st.session_state['full_val']
            swing_data = st.session_state['swing_data']

            if "error" in swing_data:
                st.error(f"Failed to fetch data for {ticker}. Please check the ticker symbol.")
            else:
                # 1. TOP VERDICT SECTION
                current_price = swing_data.get('current_price', 0)
                signal = swing_data.get('swing_signal', 'HOLD')
                confidence = swing_data.get('confidence', 0)
                fscore = fscore_data.get('score', 0)
                upside = full_val.get('upside_pct', 0)
                
                # Technical EV from swing_data
                tech_rm = swing_data.get('risk_management', {})
                tech_ev = tech_rm.get('expected_value_pct', 0) * 100 # Convert to %
                
                # Fundamental EV from full_val
                fund_ev = full_val.get('expected_value_pct', 0)
                
                # Hybrid EV (Weighted Average)
                hybrid_ev = (tech_ev * 0.5) + (fund_ev * 0.5)
                
                # Hybrid Score Calculation (40% Fundamental, 30% DCF, 30% Technical)
                f_norm = fscore / 9
                d_norm = min(max((upside + 20) / 100, 0), 1)
                t_norm = confidence if "BUY" in signal else (1 - confidence if "SELL" in signal else 0.5)
                
                hybrid_score = (f_norm * 0.4 + d_norm * 0.3 + t_norm * 0.3) * 100
                
                if hybrid_score >= 70:
                    v_class, v_text, v_sub = "verdict-buy", "STRONG BUY", "Convergent Signal: Fundamental & Technical Alignment"
                elif hybrid_score >= 45:
                    v_class, v_text, v_sub = "verdict-hold", "ACCUMULATE", "Mixed Signals: Potential Opportunity on Pullback"
                else:
                    v_class, v_text, v_sub = "verdict-sell", "AVOID / SELL", "Negative Convergence: High Structural & Momentum Risk"

                st.markdown(f"""
                <div class="verdict-container {v_class} animate-fade">
                    <p style='color:rgba(255,255,255,0.8); margin:0; text-transform:uppercase; letter-spacing:2px;'>Hybrid Intelligence Verdict for {ticker}</p>
                    <h1 class="verdict-title">{v_text}</h1>
                    <p class="verdict-score">Consensus Score: {hybrid_score:.1f}% | {v_sub}</p>
                </div>
                """, unsafe_allow_html=True)

                # 2. KEY METRICS GRID (Side-by-Side Fundamentals and Technicals)
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                
                with m_col1:
                    st.markdown(f"""
                    <div class="glass-card metric-box animate-fade">
                        <div class="metric-label">Current Price</div>
                        <div class="metric-value">${current_price:,.2f}</div>
                        <div class="metric-delta" style='color:var(--text-muted)'>Asset Value</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with m_col2:
                    ev_color = "var(--success)" if hybrid_ev > 0 else "var(--danger)"
                    st.markdown(f"""
                    <div class="glass-card metric-box animate-fade">
                        <div class="metric-label">Hybrid Expected Value</div>
                        <div class="metric-value" style='color:{ev_color}'>{hybrid_ev:+.2f}%</div>
                        <div class="metric-delta" style='color:var(--text-muted)'>Agent Combined Projection</div>
                    </div>
                    """, unsafe_allow_html=True)

                with m_col3:
                    f_color = "var(--success)" if fscore >= 7 else ("var(--warning)" if fscore >= 4 else "var(--danger)")
                    st.markdown(f"""
                    <div class="glass-card metric-box animate-fade">
                        <div class="metric-label">Financial Integrity</div>
                        <div class="metric-value" style='color:{f_color}'>{fscore}/9</div>
                        <div class="progress-bg"><div class="progress-fill" style="width:{fscore/9*100}%; background:{f_color}"></div></div>
                    </div>
                    """, unsafe_allow_html=True)

                with m_col4:
                    sig_color = "var(--success)" if "BUY" in signal else ("var(--danger)" if "SELL" in signal else "var(--warning)")
                    st.markdown(f"""
                    <div class="glass-card metric-box animate-fade">
                        <div class="metric-label">Momentum Signal</div>
                        <div class="metric-value" style='color:{sig_color}'>{signal}</div>
                        <div class="metric-delta" style='color:var(--text-muted)'>Confidence: {confidence*100:.0f}%</div>
                    </div>
                    """, unsafe_allow_html=True)

                # 3. DETAILED ANALYSIS TABS
                tab1, tab2, tab3 = st.tabs(["🚀 HYBRID EXECUTIVE SUMMARY", "💎 FUNDAMENTAL DEEP-DIVE", "📈 TECHNICAL PRECISION"])
                
                with tab1:
                    col_left, col_right = st.columns([2, 1])
                    with col_left:
                        st.markdown("### Integrated Market Context")
                        # High-End Charting
                        ohlcv = swing_data.get('ohlcv', pd.DataFrame())
                        if not ohlcv.empty:
                            fig = make_subplots(
                                rows=2, cols=1, shared_xaxes=True,
                                vertical_spacing=0.03, row_heights=[0.7, 0.3]
                            )
                            # Price & BB
                            upper, mid, lower, _, _ = swing_analyzer.bollinger_bands(ohlcv['Close'])
                            fig.add_trace(go.Candlestick(x=ohlcv.index, open=ohlcv['Open'], high=ohlcv['High'], low=ohlcv['Low'], close=ohlcv['Close'], name="Price"), row=1, col=1)
                            fig.add_trace(go.Scatter(x=ohlcv.index, y=upper, line=dict(color='rgba(255,255,255,0.2)', width=1), name="Upper BB"), row=1, col=1)
                            fig.add_trace(go.Scatter(x=ohlcv.index, y=lower, line=dict(color='rgba(255,255,255,0.2)', width=1), fill='tonexty', name="Lower BB"), row=1, col=1)
                            
                            # Volume
                            fig.add_trace(go.Bar(x=ohlcv.index, y=ohlcv['Volume'], name="Volume", marker_color="rgba(99, 102, 241, 0.4)"), row=2, col=1)
                            
                            fig.update_layout(
                                height=500, template="plotly_dark",
                                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                                xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=0, b=0)
                            )
                            st.plotly_chart(fig, use_container_width=True)

                    with col_right:
                        st.markdown("### Strategic Rationale")
                        st.markdown(f"""
                        <div class="glass-card">
                            <h4 style='margin-top:0; color:var(--primary);'>Hybrid Thesis</h4>
                            <p style='font-size:0.9rem; color:var(--text-muted);'>
                                {ticker} exhibits a <b>{v_text}</b> profile. 
                                <br><br>
                                <b>Fundamental Agent:</b> {fscore_data['category']} based on Piotroski criteria. 
                                {'Undervalued' if upside > 15 else 'Fairly Valued' if upside > -5 else 'Overvalued'} with <b>{upside:+.1f}%</b> margin.
                                <br><br>
                                <b>Technical Agent:</b> <b>{signal}</b> signal detected with <b>{confidence*100:.0f}%</b> confidence. 
                                RSI is at <b>{swing_data['rsi']['value']}</b>.
                            </p>
                            <hr style='border-color:var(--glass-border);'>
                            <p style='font-size:0.8rem; text-transform:uppercase; letter-spacing:1px;'>Agent EV Consolidation</p>
                            <div style='display:flex; justify-content:space-between; margin-bottom:10px;'>
                                <span>Fundamental EV</span>
                                <span style='color:var(--success)'>{fund_ev:+.2f}%</span>
                            </div>
                            <div style='display:flex; justify-content:space-between; margin-bottom:10px;'>
                                <span>Technical EV</span>
                                <span style='color:var(--success)'>{tech_ev:+.2f}%</span>
                            </div>
                            <div style='display:flex; justify-content:space-between; font-weight:700; border-top:1px solid var(--glass-border); padding-top:10px;'>
                                <span>Hybrid Consensus</span>
                                <span style='color:var(--primary)'>{hybrid_ev:+.2f}%</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.markdown("#### Formulaic Rationale")
                        st.latex(r"EV_{Hybrid} = \frac{EV_{Fund} + EV_{Tech}}{2}")
                        st.latex(r"EV = (P_{win} \times Profit) - (P_{loss} \times Loss)")

                with tab2:
                    st.markdown("### Fundamental Value Architecture")
                    f_col1, f_col2 = st.columns(2)
                    with f_col1:
                        st.markdown("#### Intrinsic DCF Analysis")
                        if "error" not in dcf_data:
                            st.markdown(f"""
                            <div class="glass-card">
                                <div style='display:flex; justify-content:space-between; margin-bottom:15px;'>
                                    <span style='color:var(--text-muted)'>Fair Value Estimate</span>
                                    <span style='font-size:1.5rem; font-weight:700;'>${dcf_data.get('intrinsic_value_per_share', 0):,.2f}</span>
                                </div>
                                <div style='display:flex; justify-content:space-between; margin-bottom:15px;'>
                                    <span style='color:var(--text-muted)'>Margin of Safety</span>
                                    <span style='color:var(--success)'>{dcf_data.get('margin_of_safety', 0)*100:.1f}%</span>
                                </div>
                                <div style='display:flex; justify-content:space-between;'>
                                    <span style='color:var(--text-muted)'>Terminal Growth</span>
                                    <span>{dcf_data.get('parameters', {}).get('terminal_growth', 0)*100:.1f}%</span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            st.caption("Valuation based on 10-year FCF projection and WACC discount model.")
                        else:
                            st.warning("Financial data insufficient for DCF calculation.")
                    
                    with f_col2:
                        st.markdown("#### Financial Structural Integrity (F-Score)")
                        details = fscore_data.get('details', {})
                        if details:
                            f_df = pd.DataFrame([
                                {"Criteria": k.replace("F", "").replace("_", " ").title(), "Status": "PASS ✅" if v else "FAIL ❌"}
                                for k, v in details.items()
                            ])
                            st.dataframe(f_df, hide_index=True, use_container_width=True)

                with tab3:
                    st.markdown("### Technical Momentum Precision")
                    t_col1, t_col2 = st.columns(2)
                    with t_col1:
                        st.markdown("#### Technical Oscillator Signals")
                        t_sigs = swing_data.get('signals', {})
                        for name, info in t_sigs.items():
                            color = "var(--success)" if "BUY" in info['signal'] else ("var(--danger)" if "SELL" in info['signal'] else "var(--warning)")
                            st.markdown(f"""
                            <div style='padding:15px; border-left:4px solid {color}; background:var(--glass); border-radius:8px; margin-bottom:12px;'>
                                <div style='display:flex; justify-content:space-between;'>
                                    <b style='color:var(--text-main)'>{name}</b>
                                    <span style='color:{color}; font-weight:600;'>{info['signal']}</span>
                                </div>
                                <p style='margin:5px 0 0 0; font-size:0.85rem; color:var(--text-muted);'>{info['reason']}</p>
                            </div>
                            """, unsafe_allow_html=True)
                    
                    with t_col2:
                        st.markdown("#### Trend & Volatility Metrics")
                        cross = swing_data.get('ma_cross', {})
                        rm = swing_data.get('risk_management', {})
                        
                        st.markdown(f"""
                        <div class="glass-card">
                            <p><b>Trend:</b> {cross.get('trend_status', 'N/A')}</p>
                            <p><b>200 EMA:</b> ${cross.get('ema200', 0):,.2f} ({'Above' if cross.get('price_above_ema200') else 'Below'})</p>
                            <p><b>Volatility (ATR):</b> ${swing_data.get('atr', 0):,.2f}</p>
                            <hr style='border-color:var(--glass-border);'>
                            <p style='color:var(--primary); font-weight:600;'>Execution Matrix</p>
                            <div style='display:grid; grid-template-columns: 1fr 1fr; gap:10px;'>
                                <div><small>Target</small><br><b>${rm.get('target', 0):,.2f}</b></div>
                                <div><small>Stop Loss</small><br><b>${rm.get('stop_loss', 0):,.2f}</b></div>
                                <div><small>Risk/Reward</small><br><b>1 : {rm.get('risk_reward_ratio', 0):.1f}</b></div>
                                <div><small>Win Prob.</small><br><b>{rm.get('win_probability', 0)*100:.1f}%</b></div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

elif mode == "Macro Liquidity":
    st.markdown("<h2 class='animate-fade'>Global Macro Intelligence</h2>", unsafe_allow_html=True)
    
    with st.spinner("Synchronizing Global Macro Data..."):
        latest = db.get_latest_macro()
        
    if latest:
        cols = st.columns(6)
        display_map = [
            ("DGS10", "US 10Y", "%"), ("T10Y2Y", "Yield Curve", "%"),
            ("VIXCLS", "VIX", ""), ("NET_LIQUIDITY", "Net Liq", "B"),
            ("DEXKOUS", "USD/KRW", "₩"), ("BAMLH0A0HYM2", "HY Spread", "%")
        ]
        for i, (key, label, unit) in enumerate(display_map):
            d = latest.get(key, {})
            val = d.get("current", 0)
            delta = val - d.get("prev", val)
            with cols[i]:
                st.markdown(f"""
                <div class="glass-card metric-box animate-fade">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value" style='font-size:1.4rem;'>{val:.2f}{unit}</div>
                    <div class="metric-delta" style='color:{"#10b981" if delta <=0 else "#ef4444"}'>{delta:+.2f}</div>
                </div>
                """, unsafe_allow_html=True)

    # Historical Group Charts
    st.markdown("### Strategic Market Dimensions")
    MACRO_GROUPS = {
        "Liquidity / Central Bank": ["M2SL", "WALCL", "NET_LIQUIDITY"],
        "Treasury Yields": ["DGS2", "DGS10", "T10Y2Y", "T10Y3M"],
        "Risk & Inflation": ["CPIAUCSL", "VIXCLS", "BAMLH0A0HYM2"],
    }
    grp = st.selectbox("Market Dimension", list(MACRO_GROUPS.keys()))
    
    fig_m = go.Figure()
    for t in MACRO_GROUPS[grp]:
        h = db.get_macro_history(t, days=1825)
        if h is not None and not h.empty:
            fig_m.add_trace(go.Scatter(x=h.index, y=h['value'], name=t, line=dict(width=2)))
            
    fig_m.update_layout(
        height=450, template="plotly_dark",
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0, r=0, t=10, b=0)
    )
    st.plotly_chart(fig_m, use_container_width=True)

# --- Footer ---
st.markdown("---")
st.markdown("<p style='text-align:center; color:var(--text-muted); font-size:0.8rem;'>Quant Intelligence Dashboard v4.1 Platinum | Secure Multi-Agent System | Data Unidirectionality Maintained</p>", unsafe_allow_html=True)
