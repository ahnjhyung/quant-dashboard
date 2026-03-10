"""숏스퀴즈 대시보드 페이지"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from analysis.short_squeeze import ShortSqueezeAnalyzer, THRESHOLDS, SQUEEZE_LEVELS


def render_short_squeeze():
    st.title("🚨 숏스퀴즈 포착 시스템")
    st.caption(
        "공매도 점유율 · 커버 일수 · 거래량 급등 · RSI 구간 · 감마스퀴즈 위험 종합 스코어링"
    )

    analyzer = ShortSqueezeAnalyzer()

    tab1, tab2, tab3 = st.tabs(["🔍 단일 종목 분석", "📡 워치리스트 스크리너", "ℹ️ 전략 설명"])

    # ─────────────────────────────────────────────────────────
    # TAB 1: 단일 종목 상세 분석
    # ─────────────────────────────────────────────────────────
    with tab1:
        col_l, col_r = st.columns([2, 1])
        with col_l:
            ticker = st.text_input(
                "종목 코드 (미국 주식만 공매도 데이터 제공)",
                value="GME",
                help="예: GME, AMC, NVDA — 한국 주식(.KS/.KQ)은 기술적 지표만 사용",
            )
        with col_r:
            include_opts = st.toggle("옵션 감마 분석 포함", value=False,
                                     help="ON 시 추가 시간 소요 (30일 내 콜옵션 OI 조회)")

        if st.button("🔍 분석 실행", type="primary"):
            with st.spinner(f"[{ticker}] 숏스퀴즈 분석 중..."):
                result = analyzer.analyze(ticker, include_options=include_opts)

            # ── 핵심 배너 ──────────────────────────────────
            score = result["squeeze_score"]
            level = result["level"]
            summary = result["summary"]

            if score >= 75:
                st.error(f"## {summary}")
            elif score >= 55:
                st.warning(f"## {summary}")
            elif score >= 40:
                st.info(f"## {summary}")
            else:
                st.success(f"## {summary}")

            if result.get("is_korean"):
                st.warning("⚠️ 한국 주식: Yahoo Finance 공매도 데이터 없음. Squeeze Score는 기술적 지표 기반만 계산됨.")

            if result["risk_note"] and result["risk_note"] != "특이 위험 없음":
                st.error(f"🔥 **위험 요인:** {result['risk_note']}")

            # ── 핵심 지표 ──────────────────────────────────
            st.markdown("---")
            st.subheader("📊 핵심 지표")

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric(
                "Squeeze Score",
                f"{score:.1f} / 100",
                level,
            )

            sh = result.get("short_metrics", {})
            c2.metric("공매도 점유율", f"{sh.get('short_pct_float', 0):.1%}",
                      "극단적" if sh.get("short_pct_float", 0) >= THRESHOLDS["short_float_extreme"]
                      else ("높음" if sh.get("short_pct_float", 0) >= THRESHOLDS["short_float_high"] else "보통"))
            c3.metric("커버 일수", f"{sh.get('days_to_cover', 0):.1f}일",
                      "⚠️ 탈출 어려움" if sh.get("days_to_cover", 0) >= THRESHOLDS["days_to_cover_high"] else "")
            c3.caption(f"차입비용 추정: {sh.get('borrow_rate_est', 'N/A')}")

            tech = result.get("technical", {})
            c4.metric("거래량 배수", f"{tech.get('volume_ratio', 0):.2f}x",
                      "급등" if tech.get("volume_ratio", 0) >= THRESHOLDS["volume_surge_high"] else "보통")
            c5.metric("RSI 14", f"{tech.get('rsi_14', 0):.1f}",
                      "과매도 위험" if tech.get("rsi_14", 50) < 40 else "")

            # ── Squeeze Score 게이지 ────────────────────────
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=score,
                domain={"x": [0, 1], "y": [0, 1]},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar":  {"color": "#f4a261"},
                    "steps": [
                        {"range": [0,  40], "color": "#2d2d2d"},
                        {"range": [40, 55], "color": "#3d3d00"},
                        {"range": [55, 75], "color": "#6b3a00"},
                        {"range": [75, 100], "color": "#7b0000"},
                    ],
                    "threshold": {
                        "line": {"color": "white", "width": 4},
                        "thickness": 0.75, "value": score
                    },
                },
                title={"text": f"Squeeze Score — {level}"},
            ))
            fig_gauge.update_layout(height=280, template="plotly_dark")
            st.plotly_chart(fig_gauge, use_container_width=True)

            # ── 컴포넌트 레이더 차트 ───────────────────────
            components = result.get("components", {})
            if components:
                labels = {
                    "short_float_pct": "공매도 점유율",
                    "days_to_cover":   "커버 일수",
                    "volume_surge":    "거래량 급등",
                    "momentum_5d":     "5일 모멘텀",
                    "rsi_zone":        "RSI 위험 구간",
                    "float_size_inv":  "소형 플로트",
                }
                cats   = [labels.get(k, k) for k in components]
                values = [v * 100 for v in components.values()]
                values_closed = values + [values[0]]
                cats_closed   = cats   + [cats[0]]

                fig_radar = go.Figure()
                fig_radar.add_trace(go.Scatterpolar(
                    r=values_closed, theta=cats_closed,
                    fill="toself", name="Score 기여도",
                    line_color="#f4a261",
                    fillcolor="rgba(244,162,97,0.3)",
                ))
                fig_radar.update_layout(
                    polar={"radialaxis": {"visible": True, "range": [0, 100]}},
                    showlegend=False,
                    template="plotly_dark",
                    height=380,
                    title="컴포넌트별 기여도 (가중치 적용 전)",
                )
                st.plotly_chart(fig_radar, use_container_width=True)

            # ── 기술적 상세 ─────────────────────────────────
            st.subheader("📈 기술적 분석")
            t1, t2, t3, t4 = st.columns(4)
            t1.metric("현재가", f"${tech.get('current_price', 0):,.2f}")
            t2.metric("1일 수익률", f"{tech.get('mom_1d', 0):+.2%}")
            t3.metric("5일 수익률", f"{tech.get('mom_5d', 0):+.2%}")
            t4.metric("10일 수익률", f"{tech.get('mom_10d', 0):+.2%}")

            t5, t6, t7, t8 = st.columns(4)
            t5.metric("볼린저 %B",  f"{tech.get('bb_pct_b', 0):.3f}",
                      "상단 돌파" if tech.get("bb_pct_b", 0) > 1 else
                      ("하단 돌파" if tech.get("bb_pct_b", 0) < 0 else ""))
            t6.metric("52주 내 위치", f"{tech.get('pos_in_52w_range', 0):.1%}",
                      help="0%=52주 최저, 100%=52주 최고")
            t7.metric("공매도 잔고",  f"{sh.get('shares_short', 0):,}주")
            t8.metric("유동주식수",   f"{sh.get('float_shares', 0) / 1e6:.1f}M주"
                      if sh.get("float_shares", 0) else "N/A")

            # ── 감마 분석 ───────────────────────────────────
            gamma = result.get("gamma", {})
            if gamma and gamma.get("gamma_signal") not in ["옵션 분석 생략 (스크리닝 모드 또는 한국 주식)", "옵션 데이터 없음"]:
                st.markdown("---")
                st.subheader("🎯 옵션 감마 익스포저 (감마스퀴즈 위험)")
                gep = gamma.get("gamma_exposure_pct", 0)
                if gep >= THRESHOLDS["gamma_extreme"]:
                    st.error(gamma["gamma_signal"])
                elif gep >= THRESHOLDS["gamma_high"]:
                    st.warning(gamma["gamma_signal"])
                else:
                    st.info(gamma["gamma_signal"])

                g1, g2, g3, g4 = st.columns(4)
                g1.metric("감마 익스포저", f"{gep:.2f}%")
                g2.metric("근거리 콜 OI", f"{gamma.get('call_oi_near', 0):,}")
                g3.metric("근거리 풋 OI", f"{gamma.get('put_oi_near', 0):,}")
                g4.metric("근거리 PCR",
                          str(gamma.get("near_pcr", "N/A")),
                          help="PCR < 0.7: 콜 쏠림 → 감마스퀴즈 위험")

            # ── 공매도 잔고 추이 ──────────────────────────
            st.markdown("---")
            st.subheader("📅 공매도 잔고 추이 (전월 대비)")
            with st.spinner("공매도 잔고 추이 조회..."):
                hist = analyzer.get_historical_short_interest(ticker)

            if "error" not in hist:
                h1, h2, h3 = st.columns(3)
                h1.metric("이번 달 잔고",  f"{hist.get('current_short', 0):,}주")
                h2.metric("지난 달 잔고",  f"{hist.get('prior_month_short', 0):,}주")
                h3.metric("변화율",        f"{hist.get('change_pct', 0):+.1%}",
                          delta_color="inverse")
                trend_sig = hist.get("trend_signal", "")
                if "증가" in trend_sig:
                    st.error(trend_sig)
                elif "감소" in trend_sig:
                    st.success(trend_sig)
                else:
                    st.info(trend_sig)
                st.caption(hist.get("data_note", ""))

    # ─────────────────────────────────────────────────────────
    # TAB 2: 워치리스트 스크리너
    # ─────────────────────────────────────────────────────────
    with tab2:
        st.subheader("📡 워치리스트 스크리닝")

        default_watchlist = "GME\nAMC\nBBBY\nNVDA\nAAPL\nMSFT\nTSLA\nMETA\nAMD\n005930.KS"
        tickers_input = st.text_area(
            "종목 리스트 (줄바꿈으로 구분)",
            value=default_watchlist,
            height=200,
        )
        col_a, col_b, col_c = st.columns(3)
        min_score     = col_a.slider("최소 Squeeze Score", 0, 90, 40)
        top_n         = col_b.number_input("상위 N개 표시", 1, 50, 10)
        use_options   = col_c.toggle("감마 포함", value=False,
                                     help="ON 시 종목당 ~5초 추가 소요")

        if st.button("📡 스크리닝 시작", type="primary"):
            tickers = [t.strip() for t in tickers_input.strip().split("\n") if t.strip()]
            if not tickers:
                st.warning("종목을 입력하세요")
            else:
                progress_bar = st.progress(0, text="스크리닝 중...")
                results_list = []

                for i, ticker in enumerate(tickers):
                    progress_bar.progress((i + 1) / len(tickers), text=f"분석 중: {ticker}")
                    try:
                        r = analyzer.analyze(ticker, include_options=use_options)
                        if r["squeeze_score"] >= min_score:
                            results_list.append(r)
                    except Exception as e:
                        st.warning(f"[{ticker}] 실패: {e}")

                progress_bar.empty()
                results_list.sort(key=lambda x: -x["squeeze_score"])
                results_list = results_list[:top_n]

                if not results_list:
                    st.info(f"Squeeze Score {min_score}점 이상 종목 없음")
                else:
                    # 결과 테이블
                    rows = []
                    for r in results_list:
                        sh = r.get("short_metrics", {})
                        tech = r.get("technical", {})
                        rows.append({
                            "종목":          r["ticker"],
                            "Score":         r["squeeze_score"],
                            "레벨":          r["level"],
                            "신호":          r["signal"],
                            "공매도점유율":  f"{sh.get('short_pct_float', 0):.1%}",
                            "커버일수":      f"{sh.get('days_to_cover', 0):.1f}일",
                            "거래량배수":    f"{tech.get('volume_ratio', 0):.2f}x",
                            "RSI":           f"{tech.get('rsi_14', 0):.1f}",
                            "5일수익률":     f"{tech.get('mom_5d', 0):+.2%}",
                        })

                    df = pd.DataFrame(rows)

                    def color_signal(row):
                        if row["신호"] == "ENTER":
                            return ["background-color: #1a472a"] * len(row)
                        elif row["신호"] == "PARTIAL":
                            return ["background-color: #4a3d00"] * len(row)
                        return [""] * len(row)

                    st.dataframe(
                        df.style.apply(color_signal, axis=1),
                        hide_index=True, use_container_width=True,
                    )

                    # 스코어 바 차트
                    fig_bar = px.bar(
                        df, x="종목", y="Score", color="Score",
                        color_continuous_scale=["#2d2d2d", "#6b3a00", "#b5451b", "#e63946"],
                        title="종목별 Squeeze Score 비교",
                        template="plotly_dark",
                    )
                    fig_bar.add_hline(y=75, line_dash="dot", line_color="red",
                                      annotation_text="STRONG_SQUEEZE (75)")
                    fig_bar.add_hline(y=55, line_dash="dot", line_color="orange",
                                      annotation_text="WATCH (55)")
                    fig_bar.update_layout(height=350, coloraxis_showscale=False)
                    st.plotly_chart(fig_bar, use_container_width=True)

    # ─────────────────────────────────────────────────────────
    # TAB 3: 전략 설명
    # ─────────────────────────────────────────────────────────
    with tab3:
        st.subheader("ℹ️ 숏스퀴즈 전략 설명")

        st.markdown("""
### 숏스퀴즈란?
공매도(short selling) 포지션이 누적된 종목에서 주가가 상승하면, 손실을 제한하기 위한
**강제 숏커버링(주식 매수)**이 연쇄적으로 발생하여 주가가 급등하는 현상.

### Squeeze Score 컴포넌트

| 지표 | 가중치 | 설명 |
|------|--------|------|
| 공매도 점유율 (Short Float %) | **28%** | 유동주식 대비 공매도 주수. 35% 이상 = 극단적 |
| 커버 일수 (Days to Cover) | **22%** | 공매도 전량 커버에 필요한 평균거래일수. 높을수록 탈출 어려움 |
| 거래량 급등 (Volume Surge) | **20%** | 오늘 거래량 / 20일 평균. 2배 이상 = 매수세 유입 신호 |
| 5일 모멘텀 | **15%** | 최근 5일 주가 상승률. 상승할수록 숏 손실 증가 = 커버링 압박 |
| RSI 위험 구간 | **10%** | RSI 30~50 구간에서 반등 시 숏에게 가장 위험 |
| 소형 플로트 역수 | **5%** | 유동주식수가 적을수록 스퀴즈 강도 증가 |

### 감마스퀴즈 (Gamma Squeeze)
- 투자자들이 단기 콜옵션을 대거 매수 → 마켓메이커가 델타 헤지 위해 주식 매수
- 주가 상승 → 델타 증가 → 추가 헤지 매수 → **양의 피드백 루프**
- GME, AMC 급등 사례의 핵심 메커니즘

### 진입 기준
| 레벨 | 점수 | 행동 |
|------|------|------|
| STRONG_SQUEEZE | ≥ 75점 | 즉시 모니터링, 소액 진입 검토 |
| WATCH | ≥ 55점 | 관심 목록 유지, 거래량 확인 |
| DEVELOPING | ≥ 40점 | 계속 모니터링 |
| NO_SIGNAL | < 40점 | 대기 |

### ⚠️ 주의사항
- 숏스퀴즈는 **타이밍이 전부** - 이미 급등한 종목은 역스퀴즈(롱 익스퀴즈) 위험
- 미국 주식만 Yahoo Finance 공매도 데이터 제공 (한국 주식은 KRX/DART API 별도 필요)
- 차입비용(Borrow Rate) 추정값은 업계 경험치 기반 — 실제는 브로커 확인 필요
        """)
