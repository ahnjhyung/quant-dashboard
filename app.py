"""
퀀트 대시보드 메인 앱
====================
Streamlit 멀티페이지 앱 진입점

실행 방법:
    streamlit run app.py
"""

import streamlit as st

# 페이지 기본 설정
st.set_page_config(
    page_title="퀀트 트레이딩 시스템",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 사이드바 네비게이션 ─────────────────────────
with st.sidebar:
    st.title("📈 퀀트 트레이딩")
    st.markdown("---")
    
    st.markdown("### 🗂 메뉴")
    menu = st.radio(
        "페이지 선택",
        options=[
            "🏠 홈 대시보드",
            "📊 시장 현황",
            "🏦 SEC EDGAR (미국)",
            "🇰🇷 DART (한국)",
            "💎 가치투자 스크리너",
            "📉 스윙 트레이딩",
            "🧮 파생상품 분석",
            "₿ 비트코인 온체인",
            "🚨 숏스퀴즈 포착",
            "🌏 글로벌 무역",
            "🤖 자동매매",
        ],
        label_visibility="collapsed",
    )
    
    st.markdown("---")
    st.caption("📋 현재: 페이퍼트레이딩 모드")
    st.caption("⚡ v2.0 | Quant Engine")

# ── 페이지 라우팅 ──────────────────────────────
if st.session_state.get('page_override'):
    menu = st.session_state.page_override

if "홈" in menu:
    from pages.home import render_home
    render_home()
elif "시장 현황" in menu:
    from pages.market_overview import render_market_overview
    render_market_overview()
elif "SEC EDGAR" in menu:
    from pages.sec_edgar_page import render_sec_edgar
    render_sec_edgar()
elif "DART" in menu:
    from pages.dart_page import render_dart
    render_dart()
elif "가치투자" in menu:
    from pages.value_investing_page import render_value_investing
    render_value_investing()
elif "스윙" in menu:
    from pages.swing_trading_page import render_swing_trading
    render_swing_trading()
elif "파생상품" in menu:
    from pages.derivatives_page import render_derivatives
    render_derivatives()
elif "비트코인" in menu:
    from pages.bitcoin_page import render_bitcoin
    render_bitcoin()
elif "숏스퀴즈" in menu:
    from pages.short_squeeze_page import render_short_squeeze
    render_short_squeeze()
elif "글로벌 무역" in menu:
    from pages.global_trade_page import render_global_trade
    render_global_trade()
elif "자동매매" in menu:
    from pages.auto_trading_page import render_auto_trading
    render_auto_trading()
