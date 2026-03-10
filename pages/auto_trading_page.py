"""자동매매 컨트롤 페이지"""

import streamlit as st
import json
import pandas as pd
from pathlib import Path
from auto_trading.position_manager import PositionManager
from auto_trading.signal_generator import SignalGenerator


def render_auto_trading():
    st.title("🤖 자동매매 시스템")

    # ── 페이퍼트레이딩 경고 ─────────────────────────
    st.warning("📋 **페이퍼트레이딩 모드** — KIS/Upbit API 키 설정 전까지 실거래 불가")

    # ── 설정 ─────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ 자동매매 설정")
        total_capital = st.number_input("총 투자 가능 금액 (만원)", value=1000) * 10000
        paper_mode = st.toggle("페이퍼트레이딩 모드", value=True)
        if not paper_mode:
            st.error("⚠️ 실거래 모드 — KIS/Upbit 키 필요")

    # ── 탭 구성 ───────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["📊 신호 생성", "💼 포지션 관리", "📋 거래 이력"])

    with tab1:
        st.subheader("매매 신호 생성")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**미국 주식 워치리스트**")
            stocks_input = st.text_area(
                "티커 (줄바꿈으로 구분)", value="AAPL\nMSFT\nNVDA\nGOOGL",
                height=120, label_visibility="collapsed"
            )
            watchlist_stocks = [t.strip() for t in stocks_input.split("\n") if t.strip()]
        with col_b:
            st.markdown("**한국 주식**")
            kr_input = st.text_area(
                "티커", value="005930.KS\n000660.KS",
                height=120, label_visibility="collapsed"
            )
            watchlist_kr = [t.strip() for t in kr_input.split("\n") if t.strip()]

        watchlist = watchlist_stocks + watchlist_kr

        if st.button("🤖 신호 생성 실행", type="primary"):
            with st.spinner(f"{len(watchlist)}개 종목 신호 생성 중..."):
                gen = SignalGenerator(
                    watchlist_stocks=watchlist,
                    watchlist_crypto=[],
                    paper_trading=paper_mode
                )
                result = gen.generate_stock_signals()
                gen.save_signals({"all_signals": result, "summary": {}})

            if result:
                # 결과 테이블
                df = pd.DataFrame(result)
                df_display = df[["ticker", "signal", "price", "rsi",
                                 "tech_signal", "confidence", "stop_loss", "target"]].copy()
                df_display["confidence"] = df_display["confidence"].apply(lambda x: f"{x:.0%}")
                df_display["price"] = df_display["price"].apply(lambda x: f"${x:.2f}" if x else "")

                def highlight_signal(row):
                    if row["signal"] in ["ENTER"]:
                        return ["background-color: #1a472a"] * len(row)
                    elif row["signal"] in ["AVOID"]:
                        return ["background-color: #7b2d2d"] * len(row)
                    elif row["signal"] == "PARTIAL":
                        return ["background-color: #4a3d00"] * len(row)
                    return [""] * len(row)

                st.dataframe(
                    df_display.style.apply(highlight_signal, axis=1),
                    hide_index=True, use_container_width=True
                )

                # 요약
                enter_count = sum(1 for r in result if r.get("signal") == "ENTER")
                avoid_count = sum(1 for r in result if r.get("signal") == "AVOID")
                partial_count = sum(1 for r in result if r.get("signal") == "PARTIAL")

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("스캔", f"{len(result)}개")
                m2.metric("🟢 진입", f"{enter_count}개")
                m3.metric("🟡 부분", f"{partial_count}개")
                m4.metric("🔴 회피", f"{avoid_count}개")

    with tab2:
        st.subheader("포지션 관리")
        pm = PositionManager(total_capital=total_capital, paper_trading=paper_mode)
        summary = pm.get_summary()

        # 포트폴리오 요약
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("투자금", f"₩{summary['invested']:,.0f}",
                  f"{summary['invested_pct']}%")
        c2.metric("미실현 손익", f"₩{summary['unrealized_pnl']:+,.0f}")
        c3.metric("실현 손익", f"₩{summary['total_realized_pnl']:+,.0f}")
        c4.metric("승률", f"{summary['win_rate']:.1f}%",
                  f"총 {summary['total_trades']}건")

        # 현재 포지션
        positions = summary.get("positions", [])
        if positions:
            st.markdown("**현재 보유 포지션**")
            df_pos = pd.DataFrame(positions)
            df_pos = df_pos[["ticker", "qty", "entry_price", "current_price",
                             "unrealized_pnl", "unrealized_pnl_pct",
                             "stop_loss", "take_profit"]]
            st.dataframe(df_pos, hide_index=True, use_container_width=True)

            # 청산 버튼
            st.markdown("---")
            st.markdown("**포지션 수동 청산**")
            close_ticker = st.selectbox("청산할 종목",
                                        [p["ticker"] for p in positions])
            close_price = st.number_input("청산가", value=0.0)
            if st.button("🔴 청산 실행"):
                if close_price > 0:
                    result = pm.close_position(close_ticker, close_price, "Manual")
                    if result["success"]:
                        st.success(f"✅ {close_ticker} 청산 완료")
                        st.rerun()
                    else:
                        st.error(result.get("reason", "청산 실패"))
                else:
                    st.warning("청산가를 입력하세요")

            # 신규 포지션 오픈
            st.markdown("---")
            st.markdown("**신규 포지션 추가**")
            with st.form("new_position"):
                np_ticker = st.text_input("티커")
                np_qty = st.number_input("수량", value=10, min_value=1)
                np_entry = st.number_input("진입가", value=0.0)
                np_stop = st.number_input("손절가", value=0.0)
                np_target = st.number_input("목표가", value=0.0)
                np_note = st.text_input("메모")
                submitted = st.form_submit_button("포지션 오픈")
                if submitted and np_ticker and np_entry > 0:
                    res = pm.open_position(np_ticker, np_qty, np_entry, np_stop, np_target, np_note)
                    if res["success"]:
                        st.success(f"✅ {np_ticker} 포지션 오픈")
                        st.rerun()
                    else:
                        st.error(res.get("reason"))
        else:
            st.info("현재 보유 포지션 없음")

    with tab3:
        st.subheader("거래 이력")

        # 신호 저장 파일 목록
        signal_dir = Path("auto_trading/signals")
        signal_files = sorted(signal_dir.glob("*.json"), reverse=True)[:5] if signal_dir.exists() else []

        if signal_files:
            selected_file = st.selectbox(
                "신호 파일 선택",
                signal_files,
                format_func=lambda f: f.name
            )
            with open(selected_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            signals = data.get("all_signals", [])
            if signals:
                st.dataframe(
                    pd.DataFrame(signals)[["ticker", "signal", "price", "tech_signal",
                                           "confidence", "timestamp"]],
                    hide_index=True, use_container_width=True
                )
        else:
            st.info("저장된 신호 이력이 없습니다. 신호 생성 탭에서 먼저 실행하세요.")

        # Trade history
        pm2 = PositionManager(paper_trading=paper_mode)
        trades = pm2.trade_history
        if trades:
            st.markdown("---")
            st.markdown("**청산 거래 이력**")
            df_trades = pd.DataFrame(trades)
            if not df_trades.empty:
                display_cols = [c for c in ["ticker", "entry_price", "close_price",
                                            "realized_pnl", "realized_pnl_pct",
                                            "close_reason", "close_time"] if c in df_trades.columns]
                st.dataframe(df_trades[display_cols], hide_index=True, use_container_width=True)
