"""
lite_config.py — 안드로이드/Termux용 경량화 설정
=============================================
모바일 환경의 배터리 및 CPU 부하를 줄이기 위해 루프 주기와 로깅 수준을 최적화합니다.
"""

# 스캐닝 주기 조정 (초)
POLLING_INTERVALS = {
    "polymarket_scanner": 15.0,  # 3s -> 15s (네트워크 절약)
    "azuro_feed": 30.0,          # 10s -> 30s
    "fx_sync": 300.0,            # 60s -> 300s (5분마다 환율 갱신)
    "auto_merger": 600.0,        # 300s -> 600s (10분마다 병합)
}

# 로깅 최적화
LOG_LEVEL = "INFO"               # DEBUG 배제
SUPABASE_FLUSH_INTERVAL = 10.0   # 2s -> 10s (배치 크기 키워서 DB I/O 감소)

# WebSocket 재접속 대기 시간
WS_RECONNECT_DELAY = 10.0

# 안드로이드 Wake Lock 유지 여부 (Termux API 필요)
USE_WAKE_LOCK = True
