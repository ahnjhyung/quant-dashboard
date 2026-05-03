"""
profit_monitor.py — HFT 실시간 수익 터미널 대시보드
===================================================
봇이 가동 중일 때 현재 수익/포지션 현황을 터미널에 실시간으로 출력합니다.
Paper Trading 및 실거래 모두 지원.

[사용법]
  python -m hft_arb.profit_monitor           # 5초마다 갱신
  python -m hft_arb.profit_monitor --live    # 실거래 잔고도 조회
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

# ANSI 색상 코드
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
CLEAR  = "\033[2J\033[H"   # 화면 지우기 + 커서 홈


def _fmt_usd(v: float) -> str:
    color = GREEN if v >= 0 else RED
    return f"{color}{BOLD}${v:+.4f}{RESET}"


def _fmt_pct(v: float) -> str:
    color = GREEN if v >= 0 else RED
    return f"{color}{v:+.4f}%{RESET}"


async def _get_clob_balance() -> float:
    """Polymarket CLOB 잔고 조회 (실거래 모드에서만 의미 있음)."""
    try:
        from hft_arb.clob_executor import RealClobExecutor
        executor = RealClobExecutor()
        return await executor.get_balance()
    except Exception as e:
        logger.debug(f"[Monitor] CLOB 잔고 조회 실패: {e}")
        return 0.0


async def _get_polygon_usdc_balance(address: str) -> float:
    """Web3로 Polygon USDC 온체인 잔고 조회."""
    try:
        from web3 import Web3
        USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        USDC_ABI = [{"inputs":[{"name":"account","type":"address"}],
                     "name":"balanceOf","outputs":[{"name":"","type":"uint256"}],
                     "stateMutability":"view","type":"function"}]
        w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)
        raw = usdc.functions.balanceOf(Web3.to_checksum_address(address)).call()
        return raw / 1_000_000
    except Exception as e:
        logger.debug(f"[Monitor] 온체인 잔고 조회 실패: {e}")
        return 0.0


def _load_paper_positions() -> list[dict]:
    """로그 파일에서 paper 포지션 기록 로드."""
    log_path = Path(__file__).parent / "logs" / "daemon.log"
    if not log_path.exists():
        return []

    positions = []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines[-5000:]:  # 마지막 5000줄만 파싱
            if "[Paper] 포지션 기록" in line and "EV$" in line:
                # 예: "[Paper] 포지션 기록 | ID=paper_polymarket_arb_abc | 전략=polymarket_arb | EV$0.12 (1.2000%)"
                try:
                    parts = line.split("|")
                    strategy_part = next((p for p in parts if "전략=" in p), "")
                    ev_part = next((p for p in parts if "EV$" in p), "")
                    strategy = strategy_part.split("전략=")[-1].strip() if strategy_part else "unknown"
                    ev_str = ev_part.split("EV$")[-1].split(" ")[0].strip() if ev_part else "0"
                    ev_pct_str = ev_part.split("(")[-1].split("%")[0].strip() if "(" in ev_part else "0"
                    positions.append({
                        "strategy": strategy,
                        "ev_usd": float(ev_str),
                        "ev_pct": float(ev_pct_str),
                        "ts": line[:23],
                    })
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"[Monitor] 로그 파싱 실패: {e}")
    return positions


def _render_dashboard(
    positions: list[dict],
    clob_balance: float,
    chain_balance: float,
    initial_capital: float,
    live_mode: bool,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # 집계
    total_ev_usd = sum(p["ev_usd"] for p in positions)
    poly_positions = [p for p in positions if p["strategy"] == "polymarket_arb"]
    kimchi_positions = [p for p in positions if p["strategy"] == "kimchi_arb"]
    cross_positions = [p for p in positions if p["strategy"] == "krw_cross_arb"]

    mode_str = f"{RED}🔴 REAL TRADING{RESET}" if live_mode else f"{YELLOW}📋 PAPER TRADING{RESET}"

    lines = [
        f"{BOLD}{CYAN}{'='*60}{RESET}",
        f"{BOLD}{CYAN}  HFT 차익거래 스나이퍼 봇 — 실시간 수익 모니터{RESET}",
        f"{CYAN}  {now}  |  {mode_str}",
        f"{CYAN}{'='*60}{RESET}",
        "",
        f"{BOLD}📊 포지션 통계{RESET}",
        f"  전체 체결 수     : {BOLD}{len(positions):>6}건{RESET}",
        f"  Polymarket 차익  : {BOLD}{len(poly_positions):>6}건{RESET}",
        f"  김치 프리미엄    : {BOLD}{len(kimchi_positions):>6}건{RESET}",
        f"  KRW 크로스 차익  : {BOLD}{len(cross_positions):>6}건{RESET}",
        "",
        f"{BOLD}💰 누적 기대 수익 (Paper EV 합산){RESET}",
        f"  총 EV            : {_fmt_usd(total_ev_usd)}",
        f"  초기 자본 대비   : {_fmt_pct((total_ev_usd / initial_capital * 100) if initial_capital > 0 else 0)}",
        "",
    ]

    if live_mode:
        lines += [
            f"{BOLD}🏦 실제 잔고 (온체인){RESET}",
            f"  CLOB 잔고 (USDC) : {_fmt_usd(clob_balance)}",
            f"  온체인 잔고(USDC): {_fmt_usd(chain_balance)}",
            f"  합계             : {_fmt_usd(clob_balance + chain_balance)}",
            "",
        ]

    if positions:
        lines += [
            f"{BOLD}📌 최근 체결 5건{RESET}",
        ]
        for p in positions[-5:][::-1]:
            lines.append(
                f"  [{p['ts'][:19]}] {p['strategy']:<20} "
                f"EV={_fmt_usd(p['ev_usd'])} ({_fmt_pct(p['ev_pct'])})"
            )

    lines += [
        "",
        f"{CYAN}{'='*60}{RESET}",
        f"  {YELLOW}갱신 주기 5초 | Ctrl+C 종료{RESET}",
        f"{CYAN}{'='*60}{RESET}",
    ]

    return "\n".join(lines)


async def run_monitor(live_mode: bool = False, initial_capital: float = 100.0) -> None:
    """메인 모니터링 루프."""
    address = os.getenv("POLYMARKET_ADDRESS", "")

    while True:
        try:
            positions = _load_paper_positions()

            clob_balance = 0.0
            chain_balance = 0.0
            if live_mode and address:
                clob_balance, chain_balance = await asyncio.gather(
                    _get_clob_balance(),
                    _get_polygon_usdc_balance(address),
                )

            dashboard = _render_dashboard(
                positions=positions,
                clob_balance=clob_balance,
                chain_balance=chain_balance,
                initial_capital=initial_capital,
                live_mode=live_mode,
            )

            print(CLEAR + dashboard, flush=True)

        except Exception as e:
            print(f"[Monitor] 오류: {e}")

        await asyncio.sleep(5)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="HFT 수익 모니터")
    parser.add_argument("--live", action="store_true", help="실거래 잔고 조회 활성화")
    parser.add_argument("--capital", type=float, default=100.0, help="초기 자본 (USD)")
    args = parser.parse_args()

    try:
        asyncio.run(run_monitor(live_mode=args.live, initial_capital=args.capital))
    except KeyboardInterrupt:
        print("\n[Monitor] 종료.")
