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
    if st.button("포트폴리오 대시보드 열기"):
        st.switch_page("pages/5_포트폴리오.py")

with col2:
    st.subheader("Stock Analysis")
    st.write("재무제표 분석 및 기술적 지표를 통한 개별 종목 발굴 시스템입니다.")
    if st.button("종목분석 대시보드 열기"):
        st.switch_page("pages/6_종목분석.py")

st.caption("Use the sidebar to navigate between modules.")

st.markdown("---")
st.caption("AGA Quant System v3.0")
