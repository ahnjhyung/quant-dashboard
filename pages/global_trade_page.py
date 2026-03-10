"""글로벌 무역 분석 페이지"""
import streamlit as st
import plotly.express as px
import pandas as pd
from data_collectors.korea_customs import KoreaCustomsCollector
from data_collectors.world_bank import WorldBankCollector


def render_global_trade():
    st.title("🌏 글로벌 무역 & 경제지표")
    st.caption("한국 수출입 통계 · World Bank 글로벌 경제지표")
    
    tab1, tab2 = st.tabs(["🇰🇷 한국 무역통계", "🌍 World Bank 경제지표"])
    
    with tab1:
        customs = KoreaCustomsCollector()
        year = st.selectbox("연도", [2023, 2022, 2021, 2020])
        
        if st.button("📦 한국 무역 조회"):
            with st.spinner("관세청 데이터 조회..."):
                monthly = customs.get_monthly_trade_trend(year)
                partners_exp = customs.get_top_trade_partners(year, "export")
                partners_imp = customs.get_top_trade_partners(year, "import")
            
            if monthly:
                df = pd.DataFrame(monthly)
                df["date"] = df.apply(lambda r: f"{int(r['year'])}-{int(r['month']):02d}", axis=1)
                
                import plotly.graph_objects as go
                fig = go.Figure()
                fig.add_trace(go.Bar(x=df["date"], y=df["export_usd"], name="수출", marker_color="#00b4d8"))
                fig.add_trace(go.Bar(x=df["date"], y=df["import_usd"], name="수입", marker_color="#e63946"))
                fig.update_layout(
                    title=f"{year}년 월별 수출입 추이",
                    template="plotly_dark", height=400, barmode="group",
                    yaxis_title="금액 (USD)"
                )
                st.plotly_chart(fig, use_container_width=True)
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**수출 상위 파트너**")
                if partners_exp:
                    df_e = pd.DataFrame(partners_exp)
                    fig_e = px.pie(df_e, values="amount_usd", names="country",
                                   title="수출 국가별 비중", template="plotly_dark")
                    st.plotly_chart(fig_e, use_container_width=True)
            with c2:
                st.markdown("**수입 상위 파트너**")
                if partners_imp:
                    df_i = pd.DataFrame(partners_imp)
                    fig_i = px.pie(df_i, values="amount_usd", names="country",
                                   title="수입 국가별 비중", template="plotly_dark")
                    st.plotly_chart(fig_i, use_container_width=True)
    
    with tab2:
        wb = WorldBankCollector()
        country = st.selectbox("국가", ["KR", "US", "CN", "JP", "DE"])
        indicators = {
            "GDP (현재가, USD)": "NY.GDP.MKTP.CD",
            "GDP 성장률 (%)": "NY.GDP.MKTP.KD.ZG",
            "인플레이션 (CPI %)": "FP.CPI.TOTL.ZG",
            "실업률 (%)": "SL.UEM.TOTL.ZS",
        }
        
        if st.button("🌍 World Bank 조회"):
            for name, code in indicators.items():
                with st.spinner(f"{name} 조회..."):
                    data = wb.get_indicator(country, code, years=10)
                if data:
                    df = pd.DataFrame(data).sort_values("year")
                    fig = px.line(df, x="year", y="value", title=f"{country} - {name}",
                                  template="plotly_dark")
                    st.plotly_chart(fig, use_container_width=True)
