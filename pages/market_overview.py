"""시장 현황 개요 페이지"""
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def render_market_overview():
    st.title("📊 글로벌 시장 현황")
    
    st.subheader("주요 지수")
    tickers = {
        "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Dow Jones": "^DJI",
        "코스피": "^KS11", "코스닥": "^KQ11", "Nikkei": "^N225",
        "VIX": "^VIX", "원달러": "KRW=X", "BTC": "BTC-USD",
        "WTI유": "CL=F", "금": "GC=F", "국채10년": "^TNX",
    }
    
    cols = st.columns(4)
    for i, (name, ticker) in enumerate(tickers.items()):
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = info.last_price
            prev = info.previous_close
            chg = (price - prev) / prev * 100 if prev else 0
            cols[i % 4].metric(name, f"{price:,.2f}", f"{chg:+.2f}%")
        except:
            cols[i % 4].metric(name, "N/A", "")

    st.markdown("---")
    st.subheader("6개월 지수 비교")
    
    compare_tickers = st.multiselect(
        "비교 지수 선택", list(tickers.keys()),
        default=["S&P 500", "코스피", "BTC"]
    )
    
    if compare_tickers:
        fig = go.Figure()
        for name in compare_tickers:
            try:
                data = yf.download(tickers[name], period="6mo", progress=False)
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                normalized = data["Close"] / data["Close"].iloc[0] * 100
                fig.add_trace(go.Scatter(x=data.index, y=normalized, name=name))
            except:
                pass
        
        fig.update_layout(
            title="정규화 수익률 비교 (기준: 100)",
            template="plotly_dark", height=450,
            yaxis_title="정규화 지수 (100 기준)"
        )
        st.plotly_chart(fig, use_container_width=True)
