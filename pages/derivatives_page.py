"""파생상품 분석 페이지"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from analysis.derivatives import DerivativesAnalyzer


def render_derivatives():
    st.title("🧮 파생상품 분석")
    st.caption("Black-Scholes 옵션 이론가 · Greeks · 포지션 P&L · VIX · Put-Call Ratio")

    analyzer = DerivativesAnalyzer()

    tab1, tab2, tab3, tab4 = st.tabs(
        ["🧮 옵션 계산기", "📊 포지션 P&L", "😰 VIX 분석", "🔗 옵션 체인"]
    )

    with tab1:
        st.subheader("Black-Scholes 옵션 계산기")
        c1, c2 = st.columns(2)
        with c1:
            S = st.number_input("현재가 (S)", value=150.0, step=1.0)
            K = st.number_input("행사가 (K)", value=155.0, step=1.0)
            T = st.number_input("잔존 만기 (일)", value=30, step=1)
        with c2:
            r = st.number_input("무위험이자율 (%)", value=5.0, step=0.25) / 100
            sigma = st.number_input("내재변동성 IV (%)", value=25.0, step=1.0) / 100
            option_type = st.selectbox("옵션 유형", ["call", "put"])
            q = st.number_input("배당수익률 (%)", value=0.0, step=0.1) / 100

        if st.button("📐 계산", type="primary"):
            result = analyzer.black_scholes(S, K, T, r, sigma, option_type, q)

            if "error" in result:
                st.error(result["error"])
            else:
                # 이론가
                price = result["price"]
                moneyness = result["moneyness"]
                if "ITM" in moneyness:
                    st.success(f"**이론 {option_type.upper()} 가격: ${price:.4f}** | {moneyness}")
                else:
                    st.info(f"**이론 {option_type.upper()} 가격: ${price:.4f}** | {moneyness}")

                # Greeks
                st.markdown("#### Greeks")
                g1, g2, g3, g4, g5 = st.columns(5)
                g1.metric("Delta (Δ)", f"{result['delta']:.4f}",
                          help="기초자산 1 변화 시 옵션가격 변화")
                g2.metric("Gamma (Γ)", f"{result['gamma']:.6f}",
                          help="델타의 변화율")
                g3.metric("Theta (Θ)", f"{result['theta']:.4f}/day",
                          help="1일 경과 시 옵션가치 감소")
                g4.metric("Vega (ν)", f"{result['vega']:.4f}",
                          help="변동성 1% 변화 시 옵션가격 변화")
                g5.metric("Rho (ρ)", f"{result['rho']:.4f}",
                          help="금리 1% 변화 시 옵션가격 변화")

                iv_col, it_col = st.columns(2)
                iv_col.metric("내재가치", f"${result['intrinsic_value']:.4f}")
                it_col.metric("시간가치", f"${result['time_value']:.4f}")

    with tab2:
        st.subheader("포지션 P&L 시뮬레이션")
        st.caption("현물 + 옵션 혼합 포지션의 만기 손익 시뮬레이션")

        c1, c2 = st.columns(2)
        with c1:
            spot_qty = st.number_input("현물 수량 (주)", value=100, step=10)
            spot_avg = st.number_input("현물 평균단가 ($)", value=150.0, step=1.0)
        with c2:
            st.markdown("**옵션 포지션 추가**")
            opt_type = st.selectbox("옵션 타입",
                                    ["put_long", "call_long", "put_short", "call_short"])
            opt_K = st.number_input("행사가", value=145.0, step=1.0)
            opt_premium = st.number_input("프리미엄 ($)", value=3.5, step=0.5)
            opt_qty = st.number_input("계약수", value=1, step=1)

        if st.button("📈 P&L 시뮬레이션", type="primary"):
            pnl_result = analyzer.simulate_portfolio_pnl(
                spot_qty=spot_qty,
                spot_avg_price=spot_avg,
                options=[{"type": opt_type, "K": opt_K, "premium": opt_premium, "qty": opt_qty}],
                price_range=(spot_avg * 0.7, spot_avg * 1.35)
            )

            m1, m2, m3 = st.columns(3)
            m1.metric("최대 이익", f"${pnl_result['max_profit']:,.0f}")
            m2.metric("최대 손실", f"${pnl_result['max_loss']:,.0f}")
            m3.metric("손익비", f"1:{pnl_result['risk_reward']:.1f}")

            if pnl_result.get("breakeven_prices"):
                st.info(f"손익분기점: {pnl_result['breakeven_prices']}")

            prices = pnl_result["prices"]
            spot_pnl = pnl_result["spot_pnl"]
            opt_pnl = pnl_result["option_pnl"]
            total_pnl = pnl_result["total_pnl"]

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=prices, y=spot_pnl, name="현물 P&L",
                                     line=dict(color="skyblue", dash="dot")))
            fig.add_trace(go.Scatter(x=prices, y=opt_pnl, name="옵션 P&L",
                                     line=dict(color="orange", dash="dot")))
            fig.add_trace(go.Scatter(x=prices, y=total_pnl, name="총 P&L",
                                     line=dict(color="white", width=2),
                                     fill="tozeroy",
                                     fillcolor="rgba(100,200,100,0.1)"))
            fig.add_hline(y=0, line_color="gray", line_dash="dash")
            fig.add_vline(x=spot_avg, line_dash="dot", line_color="yellow",
                          annotation_text=f"매수단가 ${spot_avg}")

            fig.update_layout(
                title="만기 포지션 P&L 시뮬레이션",
                xaxis_title="기초자산 가격 ($)",
                yaxis_title="손익 ($)",
                template="plotly_dark",
                height=450,
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("VIX 공포지수 분석")
        with st.spinner("VIX 데이터 조회 중..."):
            vix_data = analyzer.vix_analysis()

        if "error" in vix_data:
            st.error(vix_data["error"])
        else:
            vix = vix_data["vix"]
            level = vix_data["level"]
            interp = vix_data["interpretation"]

            if vix < 15:
                st.warning(interp)
            elif vix < 20:
                st.info(interp)
            elif vix > 30:
                st.error(interp)
            else:
                st.warning(interp)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("현재 VIX", str(vix))
            c2.metric("1년 최고", str(vix_data.get("vix_1y_high", "")))
            c3.metric("1년 평균", str(vix_data.get("vix_1y_avg", "")))
            c4.metric("1년 최저", str(vix_data.get("vix_1y_low", "")))
            st.metric("1년 백분위", f"{vix_data.get('vix_percentile_1y', 0):.0f}%",
                      help="현재 VIX가 1년 중 상위 몇 %에 위치하는지")

            # VIX 게이지
            fig_v = go.Figure(go.Indicator(
                mode="gauge+number",
                value=vix,
                gauge={
                    "axis": {"range": [0, 60]},
                    "bar": {"color": "orange"},
                    "steps": [
                        {"range": [0, 15], "color": "#386641"},
                        {"range": [15, 20], "color": "#a7c957"},
                        {"range": [20, 30], "color": "#f77f00"},
                        {"range": [30, 40], "color": "#e63946"},
                        {"range": [40, 60], "color": "#9b2226"},
                    ],
                },
                title={"text": level}
            ))
            fig_v.update_layout(height=300, template="plotly_dark")
            st.plotly_chart(fig_v, use_container_width=True)

    with tab4:
        st.subheader("옵션 체인 & Put-Call Ratio")
        st.caption("미국 주식 옵션만 지원 (Yahoo Finance)")
        chain_ticker = st.text_input("티커", value="AAPL", key="chain_ticker")

        if st.button("🔗 체인 조회"):
            with st.spinner("옵션 체인 조회 중..."):
                chain_data = analyzer.build_option_chain_summary(chain_ticker)

            if "error" in chain_data:
                st.error(chain_data["error"])
            else:
                pcr = chain_data["put_call_ratio"]
                pcr_signal = chain_data["pcr_signal"]

                if "Bull" in pcr_signal:
                    st.success(f"**PCR: {pcr}** — {pcr_signal}")
                elif "Bear" in pcr_signal:
                    st.error(f"**PCR: {pcr}** — {pcr_signal}")
                else:
                    st.info(f"**PCR: {pcr}** — {pcr_signal}")

                m1, m2, m3 = st.columns(3)
                m1.metric("만기일", chain_data["nearest_expiry"])
                m2.metric("콜 OI", f"{chain_data['total_call_oi']:,}")
                m3.metric("풋 OI", f"{chain_data['total_put_oi']:,}")

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**콜 옵션 체인 (내재변동성 상위)**")
                    if chain_data["call_chain"]:
                        st.dataframe(
                            pd.DataFrame(chain_data["call_chain"]),
                            hide_index=True, use_container_width=True
                        )
                with c2:
                    st.markdown("**풋 옵션 체인 (내재변동성 상위)**")
                    if chain_data["put_chain"]:
                        st.dataframe(
                            pd.DataFrame(chain_data["put_chain"]),
                            hide_index=True, use_container_width=True
                        )
