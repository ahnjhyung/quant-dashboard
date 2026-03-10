"""홈 대시보드 페이지"""

import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from config import check_config


def render_home():
    st.title("📈 퀀트 트레이딩 시스템")
    st.caption(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')} | 페이퍼트레이딩 모드")

    # ── API 상태 ──────────────────────────────────────
    with st.expander("🔑 API 연결 상태", expanded=False):
        status = check_config()
        cols = st.columns(4)
        items = list(status.items())
        for i, (svc, ok) in enumerate(items):
            cols[i % 4].metric(
                svc.upper(),
                "✅ 연결됨" if ok else "❌ 미설정",
                delta=None,
                delta_color="normal",
            )

    st.markdown("---")

    # ── 시장 지수 요약 ────────────────────────────────
    st.subheader("🌍 글로벌 시장 현황")

    indices = {
        "S&P 500": "^GSPC",
        "NASDAQ": "^IXIC",
        "코스피": "^KS11",
        "코스닥": "^KQ11",
        "VIX": "^VIX",
        "BTC": "BTC-USD",
        "원달러": "KRW=X",
        "WTI유": "CL=F",
    }

    with st.spinner("시장 데이터 로딩..."):
        cols = st.columns(4)
        for i, (name, ticker) in enumerate(indices.items()):
            try:
                t = yf.Ticker(ticker)
                info = t.fast_info
                price = info.last_price
                prev = info.previous_close
                chg = (price - prev) / prev * 100 if prev else 0
                cols[i % 4].metric(
                    name,
                    f"{price:,.2f}",
                    f"{chg:+.2f}%",
                    delta_color="normal",
                )
            except Exception:
                cols[i % 4].metric(name, "조회 실패", "")

    st.markdown("---")

    # ── 시스템 기능 카드 ──────────────────────────────
    st.subheader("🗂 분석 모듈")

    cards = [
        ("💎 가치투자", "DCF 밸류에이션, Graham Number, Piotroski F-Score, Magic Formula", "가치투자 스크리너"),
        ("📉 스윙 트레이딩", "RSI, MACD, 볼린저밴드, 이치모쿠 + 종합 진입 신호", "스윙 트레이딩"),
        ("🧮 파생상품", "Black-Scholes 그릭스, 풋콜비율, 옵션 포지션 P&L", "파생상품 분석"),
        ("₿ 비트코인", "공포탐욕지수, 반감기 사이클, 레인보우 차트, MVRV", "비트코인 온체인"),
        ("🌏 글로벌 무역", "관세청 수출입, UN Comtrade, World Bank 경제지표", "글로벌 무역"),
        ("🤖 자동매매", "실시간 신호 생성, 포지션 관리 (페이퍼트레이딩)", "자동매매"),
    ]

    cols = st.columns(3)
    for i, (icon_title, desc, page_name) in enumerate(cards):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{icon_title}**")
                st.caption(desc)
                if st.button(f"열기 →", key=f"card_{i}"):
                    st.session_state.page_override = f"{'🌏' if '무역' in icon_title else ''}{page_name}"
                    st.rerun()

    st.markdown("---")

    # ── 최근 시장 차트 (S&P 500 / BTC) ───────────────
    st.subheader("📊 최근 30일 시장 추이")

    try:
        spy = yf.download("SPY", period="1mo", progress=False)
        btc = yf.download("BTC-USD", period="1mo", progress=False)

        if isinstance(spy.columns, pd.MultiIndex):
            spy.columns = spy.columns.get_level_values(0)
        if isinstance(btc.columns, pd.MultiIndex):
            btc.columns = btc.columns.get_level_values(0)

        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=["S&P 500 (SPY)", "Bitcoin (BTC-USD)"]
        )

        fig.add_trace(
            go.Scatter(x=spy.index, y=spy["Close"], name="SPY", line=dict(color="#00b4d8")),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=btc.index, y=btc["Close"], name="BTC", line=dict(color="#f4a261")),
            row=1, col=2
        )

        fig.update_layout(
            height=300,
            template="plotly_dark",
            showlegend=False,
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.warning(f"차트 로딩 실패: {e}")
