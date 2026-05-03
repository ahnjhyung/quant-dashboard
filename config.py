"""
중앙 설정 파일
==============
.env 파일에서 모든 API 키를 로드하여
각 모듈에 제공하는 단일 진입점
"""

import os
import shutil
import certifi
from pathlib import Path
from dotenv import load_dotenv

# [SECURITY/ENVIRONMENT PATCH]
# Windows 한글 사용자명 환경에서 curl_cffi가 내장된 cacert.pem 경로를 
# 읽지 못하는 이슈(SSL 에러)를 해결하기 위해 공용 폴더로 인증서를 복사하고 
# 환경변수 CURL_CA_BUNDLE 에 등록합니다.


# 프로젝트 루트의 .env 파일 로드
_root = Path(__file__).parent
load_dotenv(_root / ".env")

# ── 안전 설정 ─────────────────────────
# 실거래 시 반드시 False로 변경 필요 (SecurityAuditor 승인 필수)
PAPER_TRADING = os.getenv("PAPER_TRADING", "False").lower() == "true"

# ── Supabase ──────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# ── AI / Embeddings ───────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ── 경제 데이터 ───────────────────────
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
ECOS_API_KEY = os.getenv("ECOS_API_KEY", "")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")

# ── 공시 / 기업 데이터 ────────────────
DART_API_KEY = os.getenv("DART_API_KEY", "")

# ── 무역 데이터 ───────────────────────
CUSTOMS_API_KEY = os.getenv("CUSTOMS_API_KEY", "")
CUSTOMS_API_ENDPOINT = os.getenv("CUSTOMS_API_ENDPOINT", "https://apis.data.go.kr/1220000/nitemtrade")
UN_COMTRADE_API_KEY = os.getenv("UN_COMTRADE_API_KEY", "")

# ── 협업 / 메모 ───────────────────────
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_PARENT_PAGE_ID = os.getenv("NOTION_PARENT_PAGE_ID", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

# ── 자동매매 API (선택) ───────────────
KIS_APP_KEY = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "")
UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY", "")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY", "")
BITHUMB_ACCESS_KEY = os.getenv("BITHUMB_ACCESS_KEY", "")
BITHUMB_SECRET_KEY = os.getenv("BITHUMB_SECRET_KEY", "")

# ── Polymarket (L2 CLOB) ──────────────
POLYMARKET_ADDRESS = os.getenv("POLYMARKET_ADDRESS", "")
POLYMARKET_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")

# ── 이메일 알림 알리미 ───────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")  # 앱 비밀번호 사용 필요
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "")

# ── 상태 체크 ────────────────────────
def check_config() -> dict:
    """설정된 API 키 상태 반환 (대시보드용)"""
    return {
        'supabase': bool(SUPABASE_URL and SUPABASE_KEY),
        'gemini': bool(GEMINI_API_KEY),
        'fred': bool(FRED_API_KEY),
        'ecos': bool(ECOS_API_KEY),
        'fmp': bool(FMP_API_KEY),
        'dart': bool(DART_API_KEY),
        'customs': bool(CUSTOMS_API_KEY),
        'un_comtrade': bool(UN_COMTRADE_API_KEY),
        'notion': bool(NOTION_API_KEY),
        'kis': bool(KIS_APP_KEY and KIS_APP_SECRET),
        'upbit': bool(UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY),
        'bithumb': bool(BITHUMB_ACCESS_KEY and BITHUMB_SECRET_KEY),
        'polymarket': bool(POLYMARKET_ADDRESS and POLYMARKET_PRIVATE_KEY),
        'email': bool(SMTP_USER and SMTP_PASS and RECIPIENT_EMAIL),
    }

if __name__ == "__main__":
    status = check_config()
    print("=== API 키 설정 상태 ===")
    emoji = {True: "✅", False: "❌"}
    for service, ok in status.items():
        print(f"  {emoji[ok]} {service}")
