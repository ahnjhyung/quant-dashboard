"""비트코인 온체인 분석 페이지"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from analysis.bitcoin_analysis import BitcoinAnalyzer


def render_bitcoin():
    st.title("₿ 비트코인 온체인 분석")
    st.caption("공포탐욕지수 · 반감기 사이클 · 레인보우 차트 · MVRV 근사")

    analyzer = BitcoinAnalyzer()

    # ── 종합 분석 실행 ──────────────────────────────────
    with st.spinner("🔍 비트코인 종합 분석 중..."):
        result = analyzer.btc_comprehensive_analysis()

    if "error" in result:
        st.error(result["error"])
        return

    price = result["current_price"]

    # ── 상단 메트릭 ────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 BTC 현재가", f"${price:,.0f}")
    col1.caption(result.get("overall_assessment", ""))

    fng = result.get("fear_greed", {})
    fng_val = fng.get("current_value", 0)
    fng_cls = fng.get("current", {}).get("classification", "")
    col2.metric("😨 공포탐욕지수", f"{fng_val}", fng_cls)

    halving = result.get("halving_cycle", {})
    col3.metric("🔄 사이클 진행률", f"{halving.get('cycle_progress_pct', 0):.1f}%")
    col3.caption(f"D+{halving.get('days_since_halving', 0)} (4차 반감기 후)")

    mvrv = result.get("mvrv", {})
    col4.metric("📊 MVRV 근사", f"{mvrv.get('mvrv_proxy', 0):.2f}")
    col4.caption(mvrv.get("signal", ""))

    st.markdown("---")

    # ── 탭 구성 ────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(
        ["😨 공포탐욕", "🔄 반감기 사이클", "🌈 레인보우 차트", "📊 MVRV 분석"]
    )

    with tab1:
        st.subheader("공포탐욕지수 분석")

        signal_box = fng.get("signal", "")
        if "매수" in signal_box or "BUY" in signal_box:
            st.success(signal_box)
        elif "매도" in signal_box or "익절" in signal_box:
            st.error(signal_box)
        else:
            st.info(signal_box)

        col_a, col_b = st.columns(2)
        col_a.metric("30일 평균", f"{fng.get('avg_30d', 0):.1f}")
        col_b.metric("7일 모멘텀", str(fng.get("momentum_7d", "")))

        # 공포탐욕 게이지
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=fng_val,
            domain={'x': [0, 1], 'y': [0, 1]},
            gauge={
                'axis': {'range': [0, 100]},
                'bar': {'color': '#f4a261'},
                'steps': [
                    {'range': [0, 25], 'color': '#d62828'},
                    {'range': [25, 45], 'color': '#f77f00'},
                    {'range': [45, 55], 'color': '#fcbf49'},
                    {'range': [55, 75], 'color': '#a7c957'},
                    {'range': [75, 100], 'color': '#386641'},
                ],
                'threshold': {'line': {'color': 'white', 'width': 4}, 'thickness': 0.75, 'value': fng_val}
            },
            title={'text': f"공포탐욕지수 · {fng_cls}"}
        ))
        fig_gauge.update_layout(height=300, template="plotly_dark")
        st.plotly_chart(fig_gauge, use_container_width=True)

        # 역사 차트
        history = fng.get("history", [])
        if history:
            df_fng = pd.DataFrame(history)
            if "timestamp" in df_fng.columns:
                df_fng["date"] = pd.to_datetime(df_fng["timestamp"], unit="s")
            elif "date" in df_fng.columns:
                df_fng["date"] = pd.to_datetime(df_fng["date"])

            if "date" in df_fng.columns and "value" in df_fng.columns:
                fig_hist = go.Figure()
                fig_hist.add_trace(go.Scatter(
                    x=df_fng["date"], y=df_fng["value"],
                    fill="tozeroy", line=dict(color="#f4a261"),
                    name="공포탐욕"
                ))
                fig_hist.add_hline(y=20, line_dash="dot", line_color="red", annotation_text="극도의 공포")
                fig_hist.add_hline(y=80, line_dash="dot", line_color="green", annotation_text="극도의 탐욕")
                fig_hist.update_layout(
                    title="60일 공포탐욕지수 추이",
                    template="plotly_dark", height=300,
                    yaxis=dict(range=[0, 100])
                )
                st.plotly_chart(fig_hist, use_container_width=True)

    with tab2:
        st.subheader("반감기 사이클 분석")
        h = halving

        col_a, col_b = st.columns(2)
        col_a.info(f"**마지막 반감기:** {h.get('last_halving')}")
        col_b.info(f"**다음 반감기:** {h.get('next_halving')} (D-{h.get('days_to_next_halving')})")

        st.markdown(f"**현재 사이클 국면:** {h.get('cycle_phase')}")
        st.success(f"**추천 전략:** {h.get('phase_signal')}")

        # 사이클 프로그레스 바
        progress = h.get("cycle_progress_pct", 0) / 100
        st.progress(progress, text=f"사이클 진행률 {h.get('cycle_progress_pct'):.1f}%")

        # 반감기 히스토리 테이블
        st.subheader("반감기 이력")
        halvings = h.get("halvings", [])
        if halvings:
            df_h = pd.DataFrame(halvings)
            st.dataframe(df_h, hide_index=True, use_container_width=True)

    with tab3:
        st.subheader("레인보우 차트 분석")
        rainbow = result.get("rainbow_chart", {})

        band = rainbow.get("current_band", "")
        premium = rainbow.get("premium_to_fair", 0)

        if "BUY" in band or "cheap" in band or "Fire" in band:
            st.success(f"**현재 밴드:** {band} — 저평가 구간!")
        elif "Bubble" in band or "SELL" in band or "FOMO" in band:
            st.error(f"**현재 밴드:** {band} — 고평가 주의!")
        else:
            st.info(f"**현재 밴드:** {band}")

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("현재가", f"${price:,.0f}")
        col_b.metric("로그회귀 공정가치", f"${rainbow.get('fair_value', 0):,.0f}")
        col_c.metric("공정가치 대비", f"{premium:+.1f}%")

        # 밴드 바 차트
        bands = rainbow.get("bands", {})
        if bands:
            band_df = pd.DataFrame([
                {"band": k, "price": v} for k, v in bands.items()
            ])
            colors = ["#8B0000", "#FF0000", "#FF4500", "#FF8C00", "#FFD700", "#9ACD32", "#228B22", "#006400", "#004400"]
            fig_rainbow = go.Figure()
            for i, (_, row) in enumerate(band_df.iterrows()):
                fig_rainbow.add_bar(
                    x=[row["price"]],
                    y=[row["band"]],
                    orientation='h',
                    marker_color=colors[i % len(colors)],
                    name=row["band"],
                )
            fig_rainbow.add_vline(x=price, line_dash="dash", line_color="white",
                                  annotation_text=f"현재 ${price:,.0f}")
            fig_rainbow.update_layout(
                template="plotly_dark", height=400,
                showlegend=False,
                xaxis_type="log",
                title="레인보우 차트 밴드 (로그 스케일)"
            )
            st.plotly_chart(fig_rainbow, use_container_width=True)

    with tab4:
        st.subheader("MVRV 근사 분석")
        st.caption("⚠️ 정확한 MVRV는 온체인 데이터 필요. 여기선 365일 평균가로 대체.")

        interp = mvrv.get("interpretation", "")
        if "BUY" in mvrv.get("signal", ""):
            st.success(interp)
        elif "SELL" in mvrv.get("signal", "") or "REDUCE" in mvrv.get("signal", ""):
            st.error(interp)
        else:
            st.info(interp)

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("현재가", f"${mvrv.get('current_price', 0):,.0f}")
        col_b.metric("실현가격(근사)", f"${mvrv.get('realized_price_proxy', 0):,.0f}")
        col_c.metric("MVRV 비율", f"{mvrv.get('mvrv_proxy', 0):.3f}")

        st.markdown("---")
        col_d, col_e, col_f = st.columns(3)
        col_d.metric("1년 최고가", f"${mvrv.get('price_1y_high', 0):,.0f}")
        col_e.metric("1년 평균가", f"${mvrv.get('price_1y_avg', 0):,.0f}")
        col_f.metric("1년 최저가", f"${mvrv.get('price_1y_low', 0):,.0f}")

    # ── 종합 신호 ──────────────────────────────────────
    st.markdown("---")
    st.subheader("🔮 종합 시장 판단")
    overall = result.get("overall_assessment", "")
    bull = result.get("bull_signals", 0)
    bear = result.get("bear_signals", 0)

    if "강한 매수" in overall:
        st.success(f"## {overall}")
    elif "강한 매도" in overall:
        st.error(f"## {overall}")
    else:
        st.warning(f"## {overall}")

    col_bull, col_bear = st.columns(2)
    col_bull.metric("🟢 상승 신호", f"{bull}개")
    col_bear.metric("🔴 하락 신호", f"{bear}개")

    breakdown = result.get("signal_breakdown", [])
    if breakdown:
        df_sig = pd.DataFrame(breakdown, columns=["지표", "신호"])
        df_sig["신호"] = df_sig["신호"].map({"bull": "🟢 강세", "bear": "🔴 약세", "neutral": "⚪ 중립"})
        st.dataframe(df_sig, hide_index=True, use_container_width=True)
