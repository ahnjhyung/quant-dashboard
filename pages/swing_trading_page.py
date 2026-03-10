"""스윙 트레이딩 신호 페이지"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from analysis.swing_trading import SwingTradingAnalyzer
from analysis.entry_timing import EntryTimingEngine


def render_swing_trading():
    st.title("📉 스윙 트레이딩 신호 분석")
    st.caption("RSI · MACD · 볼린저밴드 · 이치모쿠 · 켈리 포지션 사이징")

    analyzer = SwingTradingAnalyzer()
    engine = EntryTimingEngine()

    col_l, col_r = st.columns([2, 1])
    with col_l:
        ticker = st.text_input("티커 입력", value="AAPL",
                               help="미국: AAPL, 한국: 005930.KS, 암호화폐: BTC-USD")
        period = st.selectbox("기간", ["3mo", "6mo", "1y", "2y"], index=1)
    with col_r:
        capital = st.number_input("투자금 (만원)", min_value=100, max_value=100000,
                                  value=1000, step=100)
        capital_won = capital * 10000
        st.caption(f"₩{capital_won:,.0f}")

    if st.button("🔍 분석 실행", type="primary"):
        with st.spinner(f"[{ticker}] 분석 중..."):
            result = analyzer.full_analysis(ticker, period=period)

        if "error" in result:
            st.error(result["error"])
            return

        # ── 핵심 신호 배너 ───────────────────────────
        signal = result.get("swing_signal", "HOLD")
        confidence = result.get("confidence", 0)

        if "BUY" in signal:
            st.success(f"## {signal} | 신뢰도: {confidence:.0%}")
        elif "SELL" in signal:
            st.error(f"## {signal} | 신뢰도: {confidence:.0%}")
        else:
            st.warning(f"## {signal} | 신뢰도: {confidence:.0%}")

        # ── 주요 지표 메트릭 ─────────────────────────
        st.markdown("---")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("현재가", f"${result['current_price']:,.2f}")

        rsi = result["rsi"]["value"]
        c2.metric("RSI", f"{rsi:.1f}",
                  delta="과매도" if rsi < 30 else ("과매수" if rsi > 70 else "중립"))

        macd = result["macd"]
        c3.metric("MACD 신호", macd["signal"])

        bb = result["bollinger"]
        c4.metric("볼린저 %B", f"{bb['pct_b']:.2f}",
                  delta="하단돌파" if bb['pct_b'] < 0 else ("상단돌파" if bb['pct_b'] > 1 else "정상"))

        trend = result["ma_cross"]["current_trend"]
        c5.metric("추세", trend)

        # ── 리스크 관리 ──────────────────────────────
        rm = result.get("risk_management", {})
        st.markdown("---")
        st.subheader("🛡 리스크 관리")
        c1, c2, c3 = st.columns(3)
        c1.metric("🛑 손절가", f"${rm.get('stop_loss', 0):,.2f}")
        c2.metric("🎯 목표가", f"${rm.get('target', 0):,.2f}")
        c3.metric("⚖️ 손익비", f"1:{rm.get('risk_reward_ratio', 0):.1f}")

        # 켈리 포지션 사이징
        price = result["current_price"]
        win_return = (rm.get("target", price) - price) / price if price else 0.1
        loss_return = (price - rm.get("stop_loss", price * 0.95)) / price if price else 0.05
        win_prob = 0.5 + (confidence - 0.5) * 0.3

        sizing = engine.kelly_position_size(win_prob, win_return, loss_return, capital_won)

        st.markdown("**켈리 공식 포지션 사이징**")
        sk1, sk2, sk3 = st.columns(3)
        sk1.metric("추천 투자비율", f"{sizing['recommended_pct']:.1f}%")
        sk2.metric("추천 투자금액", f"₩{sizing['recommended_amount']:,.0f}")
        sk3.metric("예상 이익시 EV", f"{sizing['expected_value']:.2%}")

        # ── 가격 차트 ────────────────────────────────
        st.markdown("---")
        ohlcv = analyzer.get_ohlcv(ticker, period=period)
        if not ohlcv.empty:
            fig = go.Figure()

            # 캔들스틱
            fig.add_trace(go.Candlestick(
                x=ohlcv.index,
                open=ohlcv["Open"], high=ohlcv["High"],
                low=ohlcv["Low"], close=ohlcv["Close"],
                name="주가"
            ))

            # 이동평균선
            ma20 = ohlcv["Close"].rolling(20).mean()
            ma60 = ohlcv["Close"].rolling(60).mean()
            fig.add_trace(go.Scatter(x=ohlcv.index, y=ma20, name="MA20",
                                     line=dict(color="orange", width=1)))
            fig.add_trace(go.Scatter(x=ohlcv.index, y=ma60, name="MA60",
                                     line=dict(color="skyblue", width=1)))

            # 볼린저밴드
            bb_data = result["bollinger"]
            upper = bb_data.get("upper_band", 0)
            lower = bb_data.get("lower_band", 0)
            if upper and lower:
                fig.add_hline(y=upper, line_dash="dot", line_color="rgba(255,100,100,0.5)",
                              annotation_text="BB 상단")
                fig.add_hline(y=lower, line_dash="dot", line_color="rgba(100,255,100,0.5)",
                              annotation_text="BB 하단")

            fig.update_layout(
                title=f"{ticker} 가격 차트",
                template="plotly_dark",
                height=500,
                xaxis_rangeslider_visible=False,
            )
            st.plotly_chart(fig, use_container_width=True)

        # ── 이치모쿠 ─────────────────────────────────
        ichi = result.get("ichimoku", {})
        if ichi and "error" not in ichi:
            st.subheader("🌸 이치모쿠 구름")
            i1, i2, i3 = st.columns(3)
            i1.metric("전환선", f"${ichi.get('tenkan', 0):.2f}")
            i2.metric("기준선", f"${ichi.get('kijun', 0):.2f}")
            i3.metric("구름 위치", ichi.get("cloud_signal", ""))
