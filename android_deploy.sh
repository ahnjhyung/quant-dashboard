#!/bin/bash

# android_deploy.sh - Android Termux용 자동 배포 스크립트
# 사용법: termux-setup-storage 후 bash android_deploy.sh

echo "===================================================="
echo "   HFT Arbitrage Sniper - Android Deployment"
echo "===================================================="

# 1. 필수 패키지 설치
echo "[1/4] 업데이트 및 필수 패키지 설치 중..."
pkg update -y
pkg install -y python python-pip git libandroid-support-dev clang make

# 2. 가상환경 구축
echo "[2/4] 파이썬 가상환경 설정 중..."
python -m venv venv
source venv/bin/activate

# 3. 라이브러리 설치
echo "[3/4] 파이썬 라이브러리 설치 중..."
pip install --upgrade pip
pip install yfinance pandas numpy httpx requests python-dotenv web3 schedule eth-account py_clob_client

# 4. Wake Lock 설정 (화면 꺼짐 방지)
echo "[4/4] 모바일 최적화 설정 중..."
if command -v termux-wake-lock > /dev/null; then
    termux-wake-lock
    echo "Wake Lock 활성화 완료."
else
    echo "Warning: Termux API가 설치되어 있지 않습니다. 배터리 소모가 심할 수 있습니다."
fi

echo "----------------------------------------------------"
echo "배포 완료! 이제 다음 명령어로 김치 스나이퍼를 실행하세요:"
echo "source venv/bin/activate"
echo "python -m hft_arb.kimchi_sniper_daemon --live"
echo "----------------------------------------------------"
