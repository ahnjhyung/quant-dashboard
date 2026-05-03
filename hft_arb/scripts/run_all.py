"""
run_all.py — HFT 시스템 전체 원클릭 실행기
===========================================
이 스크립트 하나로 봇 데몬 + 수익 모니터를 동시에 실행합니다.
두 프로세스는 별도 터미널에서 각각 실행됩니다.

[사용법]
  python -m hft_arb.scripts.run_all            # Paper Trading (기본)
  python -m hft_arb.scripts.run_all --live     # 실거래 (주의!)
  python -m hft_arb.scripts.run_all --balance 500  # 투자 자본 설정
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent  # 투자 프로그램 개발/


def main():
    parser = argparse.ArgumentParser(description="HFT 시스템 전체 실행")
    parser.add_argument("--live",    action="store_true", help="실거래 모드 활성화")
    parser.add_argument("--balance", type=float, default=100.0, help="투자 자본 (USD, 기본 $100)")
    args = parser.parse_args()

    mode_str = "🔴 REAL TRADING (실매매)" if args.live else "📋 PAPER TRADING (모의)"
    print("=" * 55)
    print(f"  HFT 차익거래 스나이퍼 시스템")
    print(f"  모드    : {mode_str}")
    print(f"  자본    : ${args.balance:.2f}")
    print("=" * 55)

    if args.live:
        print("\n⚠️  실매매 모드입니다. 진짜 돈이 사용됩니다.")
        print("   5초 후 시작됩니다. 중단하려면 Ctrl+C\n")
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            print("취소됨.")
            sys.exit(0)

    # 공통 인자
    daemon_cmd = [
        sys.executable, "-m", "hft_arb.main_daemon",
        "--balance", str(args.balance),
    ]
    monitor_cmd = [
        sys.executable, "-m", "hft_arb.profit_monitor",
        "--capital", str(args.balance),
    ]

    if args.live:
        daemon_cmd.append("--live")
        monitor_cmd.append("--live")

    print("[1/2] 스나이퍼 봇 데몬 시작...")
    daemon_proc = subprocess.Popen(
        daemon_cmd,
        cwd=str(ROOT),
        # 데몬은 로그 파일로 출력 (별도 터미널 없이)
    )
    time.sleep(2)

    print("[2/2] 수익 모니터 시작...")
    # 모니터는 현재 터미널에서 실행 (화면 출력)
    try:
        subprocess.run(monitor_cmd, cwd=str(ROOT))
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[run_all] 종료 신호 — 데몬을 정지합니다...")
        daemon_proc.terminate()
        try:
            daemon_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            daemon_proc.kill()
        print("[run_all] 완전 종료.")


if __name__ == "__main__":
    main()
