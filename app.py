import streamlit as st

st.set_page_config(
    page_title="AGA Quant System",
    layout="wide"
)

st.title("AGA Quant System")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Global Macro Analysis")
    st.write("세계 경제의 성장과 물가 지표를 분석하여 최적의 자산 배분 비중을 도출합니다.")
    if st.button("Open Portfolio Analyzer"):
        st.switch_page("pages/5_Portfolio_Compare.py")

with col2:
    st.subheader("Fundamental & Swing Analysis")
    st.write("재무제표 분석 및 기술적 지표를 통한 개별 종목 발굴 시스템입니다.")
    if st.button("Open Strategy Dashboard"):
        st.switch_page("pages/6_Fundamental_Swing.py")

st.caption("Use the sidebar to navigate between modules.")

st.markdown("---")
st.caption("AGA Quant System v3.0")
