"""가치투자 스크리너 페이지"""
import streamlit as st
import pandas as pd
from analysis.value_investing import ValueInvestingAnalyzer


def render_value_investing():
    st.title("💎 가치투자 스크리너")
    st.caption("DCF 밸류에이션 · Graham Number · Piotroski F-Score · Magic Formula")
    
    analyzer = ValueInvestingAnalyzer()
    
    tab1, tab2, tab3 = st.tabs(["📐 종목 분석", "🪄 Magic Formula 스크리닝", "📊 DCF 계산기"])
    
    with tab1:
        ticker = st.text_input("티커 입력", value="AAPL")
        if st.button("분석", type="primary"):
            with st.spinner(f"[{ticker}] 가치 분석 중..."):
                piotroski = analyzer.piotroski_score(ticker)
                graham = analyzer.graham_number(ticker)
                dcf = analyzer.dcf_valuation(ticker)
            
            if "error" not in piotroski:
                score = piotroski["score"]
                cat = piotroski.get("category", "")
                if score >= 7:
                    st.success(f"**Piotroski F-Score: {score}/9** — {cat}")
                elif score <= 3:
                    st.error(f"**Piotroski F-Score: {score}/9** — {cat}")
                else:
                    st.warning(f"**Piotroski F-Score: {score}/9** — {cat}")
            
            c1, c2, c3 = st.columns(3)
            if graham and "error" not in graham:
                c1.metric("Graham Number", f"${graham.get('graham_number', 0):.2f}")
                c1.caption(graham.get("assessment", ""))
            
            if dcf and "error" not in dcf:
                c2.metric("DCF 내재가치", f"${dcf.get('dcf_value', 0):.2f}")
                c2.caption(f"현재가 대비: {dcf.get('upside_pct', 0):+.1f}%")
            
            per = piotroski.get("per", 0)
            pbr = piotroski.get("pbr", 0)
            if per:
                c3.metric("PER", f"{per:.1f}x")
            if pbr:
                c3.metric("PBR", f"{pbr:.2f}x")
    
    with tab2:
        candidates = st.text_area(
            "스크리닝 티커 목록 (줄바꿈)",
            value="AAPL\nMSFT\nGOOGL\nMETA\nNVDA",
            height=150
        )
        if st.button("🪄 Magic Formula 스크리닝"):
            tickers = [t.strip() for t in candidates.split("\n") if t.strip()]
            with st.spinner("Magic Formula 스크리닝 중..."):
                ranked = analyzer.magic_formula_rank(tickers)
            if "error" not in ranked:
                results = ranked.get("rankings", [])
                if results:
                    df = pd.DataFrame(results)
                    st.dataframe(df, hide_index=True, use_container_width=True)
    
    with tab3:
        st.subheader("DCF 계산기")
        c1, c2 = st.columns(2)
        with c1:
            fcf = st.number_input("FCF (백만달러)", value=100.0)
            growth_r = st.number_input("성장률 (%)", value=10.0) / 100
            terminal_g = st.number_input("영구성장률 (%)", value=2.5) / 100
        with c2:
            wacc = st.number_input("할인율 WACC (%)", value=8.0) / 100
            years = st.number_input("예측기간 (년)", value=10, min_value=5, max_value=20)
            shares = st.number_input("발행주식수 (백만주)", value=100.0)
        
        if st.button("📐 DCF 계산"):
            import numpy as np
            cash_flows = [fcf * (1 + growth_r) ** i for i in range(1, int(years) + 1)]
            terminal_value = cash_flows[-1] * (1 + terminal_g) / (wacc - terminal_g) if wacc > terminal_g else 0
            pv_cf = sum(cf / (1 + wacc) ** i for i, cf in enumerate(cash_flows, 1))
            pv_tv = terminal_value / (1 + wacc) ** years
            total_value = (pv_cf + pv_tv)
            per_share = total_value / shares if shares > 0 else 0
            
            st.success(f"**DCF 내재가치: ${per_share:.2f}/주**")
            c1, c2, c3 = st.columns(3)
            c1.metric("영업가치 PV", f"${pv_cf:.1f}M")
            c2.metric("잔존가치 PV", f"${pv_tv:.1f}M")
            c3.metric("합계 기업가치", f"${total_value:.1f}M")
