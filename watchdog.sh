#!/bin/bash

# watchdog.sh - 김프 스나이퍼 24시간 감시 스크립트

SCRIPT_NAME="kimchi_sniper_pro.py"
LOG_FILE="kimchi_pro.log"

echo "----------------------------------------------------"
echo "  KIMCHI SNIPER WATCHDOG STARTED"
echo "  Monitoring: $SCRIPT_NAME"
echo "----------------------------------------------------"

while true; do
    # 프로세스가 살아있는지 확인
    if ! pgrep -f "$SCRIPT_NAME" > /dev/null; then
        echo "[$(date)] $SCRIPT_NAME 가 중지됨. 재시작 중..."
        # 백그라운드 실행 (로그는 파일에 누적)
        python "$SCRIPT_NAME" >> "$LOG_FILE" 2>&1 &
        echo "[$(date)] 재시작 완료."
    fi
    
    # 30초마다 체크 (너무 자주 체크하면 배터리 소모)
    sleep 30
done
