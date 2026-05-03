"""
setup_polymarket.py — 폴리마켓(Polymarket) 연동 및 잔고 확인 스크립트
==================================================================
1. .env 설정 확인 (ADDRESS, PRIVATE_KEY)
2. 폴리곤 네트워크 연동 및 USDC 잔고 확인
3. CLOB API 상태 확인
"""

import asyncio
import os
import sys
from pathlib import Path

# 부모 디렉토리를 path에 추가하여 hft_arb 모듈 임포트 가능하게 설정
sys.path.append(str(Path(__file__).parent.parent.parent))

from hft_arb.clob_executor import RealClobExecutor
from dotenv import load_dotenv

async def verify_setup():
    print("=" * 60)
    print(" [Polymarket Setup Verifier] 시작")
    print("=" * 60)

    # 1. .env 로드 및 기본 체크
    load_dotenv()
    address = os.getenv("POLYMARKET_ADDRESS")
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")

    if not address or not private_key:
        print(" [X] 오류: .env 파일에 POLYMARKET_ADDRESS 또는 POLYMARKET_PRIVATE_KEY가 없습니다.")
        print("     메타마스크에서 계정 주소와 개인키(Private Key)를 추출하여 .env에 추가해주세요.")
        return

    print(f" [V] .env 설정 확인 완료 (주소: {address[:6]}...{address[-4:]})")

    # 2. ClobExecutor 초기화 및 온보딩 체크
    print(" [ ] 폴리마켓 CLOB 엔진 초기화 중...")
    try:
        executor = RealClobExecutor()
        print(" [V] CLOB 엔진 객체 생성 완료")
        
        # API Creds 유도 시도
        try:
            creds = executor.client.get_api_keys()
            if not creds:
                print(" [!] API 키가 발견되지 않았습니다. 온보딩(API 키 생성)이 필요할 수 있습니다.")
            else:
                print(" [V] API 키 확인 완료")
        except Exception:
            print(" [!] API 키 조회 실패. 신규 계정인 경우 매매 시작 시 자동 생성됩니다.")

    except Exception as e:
        print(f" [X] 오류: 엔진 초기화 실패 - {e}")
        return

    # 3. 잔고 확인
    print(" [ ] 잔고 조회 중 (Polygon USDC)...")
    try:
        # clob_executor의 get_balance 사용
        balance = await executor.get_balance()
        print(f" [V] 현재 USDC 잔고: {balance:.2f} USDC")
        
        if balance < 1.0:
            print(" [!] 경고: 잔고가 매우 부족합니다 (1 USDC 미만).")
            print("     차익거래를 위해서는 최소 5~10 USDC 이상 충전을 권장합니다.")
    except Exception as e:
        print(f" [X] 오류: 잔고 조회 실패 - {e}")

    # 4. 가스비(MATIC) 확인 - 현재 SDK에서 직접 지원하지 않으므로 생략하거나 수동 안내
    print("-" * 60)
    print(" [!] 참고: 가스비(MATIC)는 메타마스크 앱에서 직접 확인해주세요.")
    print("     (최소 1 MATIC 이상 보유 권장)")
    print("=" * 60)
    print(" 모든 점검이 완료되었습니다.")

if __name__ == "__main__":
    asyncio.run(verify_setup())
