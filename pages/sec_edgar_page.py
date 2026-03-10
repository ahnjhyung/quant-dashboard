"""SEC EDGAR 분석 페이지"""
import streamlit as st
from data_collectors.sec_edgar import SECEdgarCollector


def render_sec_edgar():
    st.title("🏦 SEC EDGAR 미국 기업 공시")
    st.caption("Securities and Exchange Commission 전자공시 · XBRL 재무데이터")
    
    collector = SECEdgarCollector()
    
    ticker = st.text_input("미국 주식 티커", value="AAPL")
    
    if st.button("📄 공시 조회"):
        with st.spinner(f"SEC EDGAR에서 [{ticker}] 데이터 조회 중..."):
            cik = collector.get_cik(ticker)
        
        if not cik:
            st.error("CIK를 찾을 수 없습니다.")
            return
        
        st.success(f"CIK: {cik}")
        
        tab1, tab2 = st.tabs(["최근 공시", "재무 데이터"])
        
        with tab1:
            filings = collector.get_recent_filings(cik, form_type="10-K", count=5)
            for f in filings[:5]:
                st.write(f"📄 {f.get('form', '')} | {f.get('filingDate', '')} | {f.get('reportDate', '')}")
        
        with tab2:
            xbrl = collector.get_financials_xbrl(cik)
            if xbrl:
                for key, val in list(xbrl.items())[:10]:
                    st.write(f"**{key}:** {val}")
