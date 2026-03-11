"""
KRX 전종목 자동 티커 조회 모듈
================================
KRX(한국거래소) OpenAPI로 KOSPI/KOSDAQ 전종목 코드를 캐싱하고
회사명 → 티커(xxxxx.KS / xxxxx.KQ) 자동 매핑을 제공합니다.

수동 ticker_mapper.py의 오류를 방지하기 위해 KRX 공식 데이터를 사용합니다.
"""

import requests
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# 캐시 파일 (하루 1회 갱신)
_CACHE_FILE = Path(__file__).parent.parent / ".krx_ticker_cache.json"
_CACHE_TTL_HOURS = 24

# KRX OpenAPI 엔드포인트
_KRX_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
_KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "http://data.krx.co.kr/",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

# 메모리 캐시 (프로세스 내 반복 조회 제거)
_memory_cache: dict[str, str] = {}  # 회사명 → 티커
_cache_loaded = False


def _fetch_krx_all_stocks() -> dict[str, str]:
    """KRX에서 KOSPI + KOSDAQ 전종목을 가져와 {회사명: 티커} 딕셔너리 반환."""
    result: dict[str, str] = {}

    for mkt_id, suffix in [("STK", ".KS"), ("KSQ", ".KQ")]:
        try:
            payload = {
                "bld": "dbms/comm/finder/finder_stkisu",
                "locale": "ko_KR",
                "mktsel": mkt_id,
                "typeNo": "0",
                "efhrDd": datetime.now().strftime("%Y%m%d"),
            }
            r = requests.post(
                _KRX_URL, data=payload, headers=_KRX_HEADERS, timeout=15
            )
            r.raise_for_status()
            data = r.json()

            for item in data.get("block1", []):
                short_code = item.get("short_code", "").strip()
                name = item.get("codeName", "").strip()
                if short_code and name:
                    ticker = f"{short_code}{suffix}"
                    result[name] = ticker
                    # 약칭 처리: "삼성전자우" → 추가, 원본도 보존

            logger.info(f"KRX {mkt_id}: {len([v for v in result.values() if v.endswith(suffix)])}개 종목 로드")
            time.sleep(0.3)  # rate limit

        except Exception as e:
            logger.warning(f"KRX {mkt_id} 조회 실패: {e}")

    return result


def _load_cache() -> dict[str, str]:
    """로컬 캐시 파일 로드. TTL 초과 시 None 반환."""
    global _memory_cache, _cache_loaded
    if _cache_loaded and _memory_cache:
        return _memory_cache

    if _CACHE_FILE.exists():
        try:
            raw = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            saved_at = datetime.fromisoformat(raw.get("saved_at", "2000-01-01"))
            if datetime.now() - saved_at < timedelta(hours=_CACHE_TTL_HOURS):
                _memory_cache = raw.get("data", {})
                _cache_loaded = True
                logger.debug(f"KRX 캐시 로드: {len(_memory_cache)}개")
                return _memory_cache
        except Exception as e:
            logger.warning(f"KRX 캐시 읽기 실패: {e}")

    return {}


def _save_cache(data: dict[str, str]) -> None:
    """캐시를 파일에 저장."""
    try:
        _CACHE_FILE.write_text(
            json.dumps({"saved_at": datetime.now().isoformat(), "data": data},
                       ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"KRX 캐시 저장 실패: {e}")


def refresh_cache() -> dict[str, str]:
    """강제로 KRX에서 새 데이터를 받아 캐시 갱신."""
    global _memory_cache, _cache_loaded
    data = _fetch_krx_all_stocks()
    if data:
        _save_cache(data)
        _memory_cache = data
        _cache_loaded = True
    return data


def get_all_tickers() -> dict[str, str]:
    """회사명 → 티커 전체 딕셔너리 반환 (캐시 우선, 없으면 KRX 호출)."""
    cached = _load_cache()
    if cached:
        return cached
    return refresh_cache()


def search_ticker(company_name: str) -> Optional[str]:
    """
    회사명으로 티커 검색 (KRX 공식 데이터 기반).

    Args:
        company_name: 회사명 (예: "유바이오로직스", "삼성전자")
    Returns:
        티커 문자열 (예: "206650.KQ") 또는 None
    """
    all_tickers = get_all_tickers()
    if not all_tickers:
        return None

    # 1. 정확 매칭
    if company_name in all_tickers:
        return all_tickers[company_name]

    # 2. 부분 매칭 (회사명이 포함된 경우)
    name_lower = company_name.lower().replace(" ", "")
    candidates = []
    for name, ticker in all_tickers.items():
        n = name.lower().replace(" ", "")
        if name_lower in n or n in name_lower:
            candidates.append((name, ticker, abs(len(n) - len(name_lower))))

    if candidates:
        # 길이 차이가 가장 적은 것 선택
        candidates.sort(key=lambda x: x[2])
        best_name, best_ticker, _ = candidates[0]
        logger.info(f"KRX 부분매칭: '{company_name}' → '{best_name}' ({best_ticker})")
        return best_ticker

    # 3. KRX API 직접 검색 (캐시에 없는 경우)
    try:
        payload = {
            "bld": "dbms/comm/finder/finder_stkisu",
            "locale": "ko_KR",
            "searchText": company_name,
            "mktsel": "ALL",
            "typeNo": "0",
            "efhrDd": datetime.now().strftime("%Y%m%d"),
        }
        r = requests.post(_KRX_URL, data=payload, headers=_KRX_HEADERS, timeout=8)
        data = r.json()
        block = data.get("block1", [])
        if block:
            item = block[0]
            code = item["short_code"].strip()
            mkt = item.get("marketCode", "KSQ")
            suffix = ".KS" if mkt == "STK" else ".KQ"
            ticker = f"{code}{suffix}"
            logger.info(f"KRX 직접검색: '{company_name}' → {ticker}")
            return ticker
    except Exception as e:
        logger.warning(f"KRX 직접검색 실패 '{company_name}': {e}")

    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== KRX 자동 티커 조회 테스트 ===")
    tests = ["유바이오로직스", "삼성전자", "SK하이닉스", "현대차", "카카오페이", "없는회사"]
    for name in tests:
        ticker = search_ticker(name)
        print(f"  {name:15s} → {ticker or 'NOT FOUND'}")
