import streamlit as st

st.set_page_config(
    page_title="AGA 퀀트 시스템 | AI 통합 투자 분석",
    layout="wide"
)

# Global Font Styling
st.markdown("""
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");
* { font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', 'Segoe UI', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif; }
</style>
""", unsafe_allow_html=True)

st.title("AGA 퀀트 시스템 (Premium)")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("매크로 분석 (Macro Analysis)")
    st.write("글로벌 매크로 국면과 거시 경제 지표를 분석하여 최적의 자산 배분 비중과 리스크를 관리합니다.")
    if st.button("포트폴리오/매크로 대시보드 열기"):
        st.switch_page("pages/5_포트폴리오.py")

with col2:
    st.subheader("마이크로 분석 (Micro Analysis)")
    st.write("개별 기업의 재무 건전성, 내재 가치 평가 및 기술적 매매 신호를 종합하여 기대값을 산출합니다.")
    if st.button("종목/마이크로 분석 대시보드 열기"):
        st.switch_page("pages/6_종목분석.py")

st.caption("사이드바 메뉴를 통해서도 각 분석 모드로 바로 이동하실 수 있습니다.")

st.markdown("---")
st.caption("AGA Quant System v4.5 Premium Edition")
