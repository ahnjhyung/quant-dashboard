"""DART 한국 공시 페이지"""
import streamlit as st
import pandas as pd
from data_collectors.open_dart import OpenDartCollector


def render_dart():
    st.title("🇰🇷 Open DART 한국 기업 공시")
    st.caption("금융감독원 전자공시 · 재무제표 · 대주주 · 배당 정보")
    
    collector = OpenDartCollector()
    
    company = st.text_input("기업명", value="삼성전자")
    year = st.number_input("사업연도", value=2023, min_value=2000, max_value=2025)
    
    if st.button("🔍 조회"):
        with st.spinner(f"DART에서 [{company}] 조회 중..."):
            corps = collector.search_corp(company)
        
        if not corps:
            st.error("기업을 찾을 수 없습니다.")
            return
        
        corp = corps[0]
        st.success(f"✅ {corp['corp_name']} (종목코드: {corp['stock_code']})")
        
        tab1, tab2, tab3 = st.tabs(["재무제표", "최근 공시", "배당정보"])
        
        with tab1:
            stmt = collector.get_financial_statements(corp['corp_code'], year)
            if stmt and 'income_statement' in stmt:
                st.markdown("**손익계산서**")
                df = pd.DataFrame(stmt['income_statement'])[['account_nm', 'thstrm_amount']].rename(
                    columns={'account_nm': '계정', 'thstrm_amount': '당기금액'}
                )
                st.dataframe(df, hide_index=True, use_container_width=True)
                
                st.markdown("**재무상태표**")
                df2 = pd.DataFrame(stmt['balance_sheet'])[['account_nm', 'thstrm_amount']].rename(
                    columns={'account_nm': '계정', 'thstrm_amount': '당기금액'}
                )
                st.dataframe(df2, hide_index=True, use_container_width=True)
        
        with tab2:
            disclosures = collector.get_disclosure_list(corp['corp_code'])
            for d in disclosures[:10]:
                st.write(f"📄 {d.get('rcept_dt', '')} | {d.get('report_nm', '')}")
        
        with tab3:
            dividends = collector.get_dividend_info(corp['corp_code'], year)
            if dividends:
                st.dataframe(pd.DataFrame(dividends), hide_index=True, use_container_width=True)
            else:
                st.info("배당 데이터 없음")
