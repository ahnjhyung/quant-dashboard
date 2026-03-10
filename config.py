"""
중앙 설정 파일
==============
.env 파일에서 모든 API 키를 로드하여
각 모듈에 제공하는 단일 진입점
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트의 .env 파일 로드
_root = Path(__file__).parent
load_dotenv(_root / ".env")

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
    }


if __name__ == "__main__":
    status = check_config()
    print("=== API 키 설정 상태 ===")
    emoji = {True: "✅", False: "❌"}
    for service, ok in status.items():
        print(f"  {emoji[ok]} {service}")
