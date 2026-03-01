import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ==========================================
# PAGE CONFIG
# ==========================================
st.set_page_config(page_title="Quant Market Dashboard", layout="wide")
st.title("📈 Quant Market Dashboard (Personal Analysis)")

# ==========================================
# DATA FETCHING
# ==========================================
@st.cache_data(ttl=3600) # Cache data for 1 hour to prevent constant API calls
def load_data(period="1y"):
    tickers = {
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "KOSPI": "^KS11",
        "Gold": "GC=F",
        "Bitcoin": "BTC-USD",
        "US 10Y Yield": "^TNX",
        "VIX": "^VIX",
        "Dollar Index": "DX-Y.NYB",
        "Crude Oil": "CL=F"
    }
    
    # Download data from Yahoo Finance
    df = yf.download(list(tickers.values()), period=period)['Close']
    
    # Rename columns to readable names
    rename_dict = {v: k for k, v in tickers.items()}
    df.rename(columns=rename_dict, inplace=True)
    
    # Forward fill missing data (e.g., weekends for crypto vs stocks)
    df.fillna(method='ffill', inplace=True)
    df.dropna(inplace=True)
    return df

# Sidebar Controls
st.sidebar.header("Settings")
period_select = st.sidebar.selectbox("Select Time Period", ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"], index=3)

# Load the data
with st.spinner("Fetching Market Data..."):
    df_prices = load_data(period=period_select)
    df_returns = df_prices.pct_change().dropna()

# ==========================================
# 1. CORRELATION HEATMAP
# ==========================================
st.subheader("🔗 Cross-Asset Correlation Heatmap")
st.markdown("자산 간의 상관관계를 나타냅니다. 1에 가까울수록 같이 움직이고, -1에 가까울수록 반대로 움직입니다.")

# Calculate Pearson correlation
corr_matrix = df_returns.corr()

fig_corr = px.imshow(
    corr_matrix, 
    text_auto=".2f", 
    aspect="auto", 
    color_continuous_scale="RdBu_r",
    zmin=-1, zmax=1
)
fig_corr.update_layout(margin=dict(l=0, r=0, b=0, t=30))
st.plotly_chart(fig_corr, use_container_width=True)

# ==========================================
# 2. RISK VS RETURN SCATTER PLOT
# ==========================================
st.subheader("⚖️ Risk vs Return (Volatility vs Performance)")
st.markdown("수익률(Return)과 변동성(Risk)을 비교합니다. 우측 상단일수록 High Risk / High Return 입니다.")

# Calculate annualized return and volatility
# Only include actual investable assets for risk vs return
# The user wants 10Y Yield (Bond proxy) and Dollar Index (Currency proxy) included, but NOT VIX.
macro_indicators = ["VIX"]
investable_assets = [col for col in df_returns.columns if col not in macro_indicators]
df_returns_assets = df_returns[investable_assets]

annual_factor = 252 # trading days in a year
returns_annual = df_returns_assets.mean() * annual_factor * 100
volatility_annual = df_returns_assets.std() * (annual_factor ** 0.5) * 100

df_risk_return = pd.DataFrame({
    'Asset': returns_annual.index,
    'Annualized Return (%)': returns_annual.values,
    'Annualized Volatility (%)': volatility_annual.values
})

fig_scatter = px.scatter(
    df_risk_return, 
    x='Annualized Volatility (%)', 
    y='Annualized Return (%)', 
    text='Asset',
    size='Annualized Volatility (%)',
    color='Annualized Return (%)',
    color_continuous_scale="Viridis",
    height=600
)
fig_scatter.update_traces(textposition='top center', marker=dict(line=dict(width=1, color='DarkSlateGrey')))
# Add zero lines
fig_scatter.add_vline(x=0, line_dash="dash", line_color="gray")
fig_scatter.add_hline(y=0, line_dash="dash", line_color="gray")

st.plotly_chart(fig_scatter, use_container_width=True)

# ==========================================
# 3. NORMALIZED PERFORMANCE TIMELINE (Log Scale)
# ==========================================
st.subheader("🎢 Normalized Asset Performance (Log Scale)")
st.markdown("선택한 기간(100포인트 기준) 동안의 누적 수익률 흐름을 **로그 스케일(Log Scale)**로 비교합니다. 비트코인처럼 변동폭이 너무 큰 자산 때문에 다른 자산들이 수평선처럼 보이는 것을 방지합니다.")

selected_assets = st.multiselect(
    "Select Assets to Compare:", 
    options=investable_assets,
    default=["S&P 500", "Bitcoin", "Gold", "KOSPI"]
)

if selected_assets:
    # Normalize prices to 100 at the start of the selected period
    df_norm = (df_prices[selected_assets] / df_prices[selected_assets].iloc[0]) * 100
    
    fig_line = px.line(df_norm, x=df_norm.index, y=selected_assets)
    fig_line.update_layout(
        yaxis_title="Normalized Value (Base 100, Log Scale)", 
        xaxis_title="Date", 
        hovermode="x unified",
        yaxis_type="log" # [NEW] Apply Log Scale to Y-axis
    )
    st.plotly_chart(fig_line, use_container_width=True)
else:
    st.info("Please select at least one asset to display the timeline.")

# ==========================================
# 4. DRAWDOWN (How far from the top?)
# ==========================================
st.subheader("📉 Current Drawdown")
st.markdown("최고점 대비 현재 얼마나 하락해 있는지를 보여줍니다. (클수록 많이 빠진 상태)")

rolling_max = df_prices[investable_assets].cummax()
drawdown = (df_prices[investable_assets] / rolling_max - 1) * 100
current_drawdown = drawdown.iloc[-1].sort_values()

fig_bar = px.bar(
    x=current_drawdown.index, 
    y=current_drawdown.values, 
    text=current_drawdown.values.round(2),
    color=current_drawdown.values,
    color_continuous_scale="Reds_r"
)
fig_bar.update_layout(yaxis_title="Drawdown (%)", xaxis_title="Asset", showlegend=False)
fig_bar.update_traces(texttemplate='%{text}%', textposition='outside')
st.plotly_chart(fig_bar, use_container_width=True)
