"""
회사명 → yfinance 티커 매핑 유틸리티
=====================================
뉴스 스크래핑으로 파싱된 한글 회사명을 yfinance에서 조회 가능한
종목코드(KRX: XXXXXX.KS/.KQ, US: TICKER)로 변환합니다.

우선순위:
  1. COMPANY_TO_TICKER 정적 테이블 (빠름, 정확)
  2. 미매핑 시 None 반환 → 현재가 조회 생략
"""

# ── 한국 주요 상장사 매핑 (코스피 + 코스닥 주요 종목) ────────────────
COMPANY_TO_TICKER: dict[str, str] = {
    # ── 대형주 (코스피) ──────────────────────────
    "삼성전자":       "005930.KS",
    "SK하이닉스":     "000660.KS",
    "LG에너지솔루션": "373220.KS",
    "삼성바이오로직스":"207940.KS",
    "현대차":         "005380.KS",
    "현대자동차":     "005380.KS",
    "기아":           "000270.KS",
    "기아차":         "000270.KS",
    "POSCO홀딩스":    "005490.KS",
    "포스코홀딩스":   "005490.KS",
    "POSCO":          "005490.KS",
    "LG화학":         "051910.KS",
    "삼성SDI":        "006400.KS",
    "카카오":         "035720.KS",
    "NAVER":          "035420.KS",
    "네이버":         "035420.KS",
    "SK텔레콤":       "017670.KS",
    "KT":             "030200.KS",
    "셀트리온":       "068270.KS",
    "현대모비스":     "012330.KS",
    "현대글로비스":   "086280.KS",
    "롯데케미칼":     "011170.KS",
    "GS칼텍스":       "078930.KS",
    "한국전력":       "015760.KS",
    "한화에어로스페이스": "012450.KS",
    "한화":           "000880.KS",
    "HD현대":         "267250.KS",
    "두산에너빌리티": "034020.KS",
    "두산":           "000150.KS",
    "기업은행":       "024110.KS",
    "하나금융지주":   "086790.KS",
    "하나금융":       "086790.KS",
    "우리금융지주":   "316140.KS",
    "우리금융":       "316140.KS",
    "KB금융":         "105560.KS",
    "신한지주":       "055550.KS",
    "신한금융":       "055550.KS",
    "메리츠금융지주": "138040.KS",
    "삼성생명":       "032830.KS",
    "삼성화재":       "000810.KS",
    "LG전자":         "066570.KS",
    "LG이노텍":       "011070.KS",
    "SK이노베이션":   "096770.KS",
    "SK":             "034730.KS",
    "S-Oil":          "010950.KS",
    "코스모신소재":   "005070.KS",
    "롯데쇼핑":       "023530.KS",
    "신세계":         "004170.KS",
    "현대백화점":     "069960.KS",
    "이마트":         "139480.KS",
    "CJ제일제당":     "097950.KS",
    "CJ":             "001040.KS",
    "오리온":         "271560.KS",
    "농심":           "004370.KS",
    "아모레퍼시픽":   "090430.KS",
    "LG생활건강":     "051900.KS",
    "고려아연":       "010130.KS",
    "OCI홀딩스":      "010060.KS",
    "한미반도체":     "042700.KS",
    "한미약품":       "128940.KS",
    "유한양행":       "000100.KS",
    "종근당":         "185750.KS",
    "대웅제약":       "069620.KS",
    "제넥신":         "095700.KS",
    "HLB":            "028300.KS",
    "인터파크":       "108790.KS",
    # ── 코스닥 주요 종목 ─────────────────────────
    "에코프로비엠":   "247540.KQ",
    "에코프로":       "086520.KQ",
    "에코프로머티":   "450080.KQ",
    "엔씨소프트":     "036570.KQ",
    "카카오게임즈":   "293490.KQ",
    "크래프톤":       "259960.KS",
    "펄어비스":       "263750.KQ",
    "컴투스":         "078340.KQ",
    "셀트리온제약":   "068760.KQ",
    "셀트리온헬스케어":"091990.KQ",
    "레인보우로보틱스":"277810.KQ",
    "유바이오로직스": "206650.KQ",

    "아시아경제":     "046970.KQ",
    "반도체":         "000660.KS",  # 뉴스 일반 키워드 → SK하이닉스 대표
    "티와이홀딩스":   "363280.KQ",
    "티씨케이":       "064760.KQ",
    "Granite":        "GRNT",       # Granite Ridge Resources (US)
    # ── 한국 ETF (KODEX / TIGER / ARIRANG 시리즈) ──────────────────
    "KODEX200":          "069500.KS",
    "KODEX레버리지":  "122630.KS",    # KOSPI200 2배
    "KODEX인버스":   "114800.KS",    # KOSPI200 인버스
    "KODEX코스닥150":  "229200.KS",
    "KODEX코스닥150레버리지": "233740.KS",
    "KODEX나스닥100":  "379800.KS",
    "KODEX금실물다":  "132030.KS",    # KRX 금 ETF
    "KODEX미달러본드": "304660.KS",
    "KODEX삼성그룹":  "091180.KS",
    "KODEXSK그룹":     "453580.KS",
    "TIGER200":          "102110.KS",    # KOSPI200 쫐종 (삼성쫐자증)
    "TIGER코스닥150":  "232080.KS",
    "TIGER나스닥100":  "133690.KS",
    "TIGER200IT":        "157490.KS",
    "TIGER200부동산":  "329200.KS",
    "TIGER미국달러단기채권": "305080.KS",
    # ── 미국 주요 종목 ────────────────────────────────────────────
    "Apple":          "AAPL",
    "Microsoft":      "MSFT",
    "Tesla":          "TSLA",
    "NVIDIA":         "NVDA",
    "Alphabet":       "GOOGL",
    "Google":         "GOOGL",
    "Amazon":         "AMZN",
    "Meta":           "META",
    "Netflix":        "NFLX",
    # ── 미국 ETF ─────────────────────────────────────────────────────
    "IVV":            "IVV",      # iShares S&P500 (SPY와 동일 지수)
    "VOO":            "VOO",      # Vanguard S&P500
    "IAU":            "IAU",      # iShares 금 ETF (GLD와 동일 기초)
    "IBIT":           "IBIT",     # iShares 비트코인 ETF
    "FBTC":           "FBTC",     # Fidelity 비트코인 ETF
    "SOXX":           "SOXX",     # iShares 반도체 ETF
    "SMH":            "SMH",      # VanEck 반도체 ETF
    "SOXL":           "SOXL",     # Direxion 반도체 3배
    "TQQQ":           "TQQQ",     # ProShares 나스닥 3배
    "UPRO":           "UPRO",     # ProShares S&P500 3배
    "UVXY":           "UVXY",     # ProShares VIX 1.5배
    "VIX":            "^VIX",     # CBOE 변동성 지수
}

# 티커 → 한글명 역방향 매핑 (이메일 출력용)
TICKER_TO_KR: dict[str, str] = {v: k for k, v in COMPANY_TO_TICKER.items()}

# 추가 별칭 (여러 이름이 같은 티커를 가리킬 때 표시명 우선 순위 지정)
TICKER_KR_DISPLAY: dict[str, str] = {
    "005930.KS":  "삼성전자",
    "000660.KS":  "SK하이닉스",
    "105560.KS":  "KB금융",
    "055550.KS":  "신한지주",
    "086790.KS":  "하나금융지주",
    "316140.KS":  "우리금융지주",
    "005380.KS":  "현대차",
    "000270.KS":  "기아",
    "373220.KS":  "LG에너지솔루션",
    "006400.KS":  "삼성SDI",
    "096770.KS":  "SK이노베이션",
    "051910.KS":  "LG화학",
    "035420.KS":  "NAVER",
    "035720.KS":  "카카오",
    "068270.KS":  "셀트리온",
    "207940.KS":  "삼성바이오로직스",
    "206650.KQ":  "유바이오로직스",

    "046970.KQ":  "아시아경제",
    "086520.KQ":  "에코프로",
    "247540.KQ":  "에코프로비엠",
    # ── ETF 한글명 ─────────────────────────────────────────────────────
    # 한국 ETF
    "069500.KS":  "KODEX 200",
    "102110.KS":  "TIGER 200",
    "122630.KS":  "KODEX 레버리지",
    "114800.KS":  "KODEX 인버스",
    "229200.KS":  "KODEX 코스닥150",
    "233740.KS":  "KODEX 코스닥150 레버리지",
    "379800.KS":  "KODEX 나스닥100",
    "133690.KS":  "TIGER 나스닥100",
    "132030.KS":  "KODEX 금실물다(KRX 금ETF)",
    "232080.KS":  "TIGER 코스닥150",
    "157490.KS":  "TIGER 200 IT",
    # 미국 ETF
    "SPY":        "S&P500 ETF(SPY)",
    "IVV":        "S&P500 ETF(IVV)",
    "VOO":        "S&P500 ETF(VOO)",
    "QQQ":        "나스닥100 ETF(QQQ)",
    "TQQQ":       "나스닥 3배(TQQQ)",
    "UPRO":       "S&P500 3배(UPRO)",
    "GLD":        "금 ETF(GLD)",
    "IAU":        "금 ETF(IAU)",
    "TLT":        "미국 장기채 ETF",
    "HYG":        "하이일드 채권 ETF",
    "SOXX":       "반도체 ETF(SOXX)",
    "SMH":        "반도체 ETF(SMH)",
    "SOXL":       "반도체 3배(SOXL)",
    "IBIT":       "비트코인 ETF(iShares)",
    "FBTC":       "비트코인 ETF(Fidelity)",
    # 암호화폐
    "BTC-USD":    "비트코인",
    "ETH-USD":    "이더리움",
    "SOL-USD":    "솔라나",
    # 미국 주식
    "AAPL":       "애플",
    "NVDA":       "엔비디아",
    "TSLA":       "테슬라",
    # 지수
    "^GSPC":      "S&P500 지수",
    "^IXIC":      "나스닥 종합지수",
    "^VIX":       "VIX 변동성지수",
    "069500.KS":  "KODEX 200(KOSPI200)",
}



def name_to_ticker(company_name: str) -> str | None:
    """
    뉴스에서 파싱된 회사명을 yfinance 티커로 변환합니다.

    우선순위:
    1. COMPANY_TO_TICKER 수동 매핑 정확 일치
    2. COMPANY_TO_TICKER 부분 일치
    3. KRX OpenAPI 자동 조회 (fallback — 수동 매핑 미등록 시)

    Args:
        company_name: 뉴스 제목에서 추출된 회사명 문자열
    Returns:
        yfinance 티커 문자열 or None (미매핑 시)
    """
    # 1. 정확 일치
    if company_name in COMPANY_TO_TICKER:
        return COMPANY_TO_TICKER[company_name]

    # 2. 부분 일치 (회사명이 key에 포함되거나 key가 회사명에 포함)
    for cn, ticker in COMPANY_TO_TICKER.items():
        if cn in company_name or company_name in cn:
            return ticker

    # 3. KRX OpenAPI 자동 조회 (fallback)
    try:
        from data_collectors.krx_ticker_resolver import search_ticker as _krx_search
        krx_ticker = _krx_search(company_name)
        if krx_ticker:
            # 현재 세션 캐시에 등록 해두기 (차시 조회 최적화)
            COMPANY_TO_TICKER[company_name] = krx_ticker
            return krx_ticker
    except Exception:
        pass

    return None


def ticker_display_name(ticker: str) -> str:
    """
    티커를 한글 표시명으로 변환합니다. 없으면 티커 그대로 반환.
    """
    return TICKER_KR_DISPLAY.get(ticker, TICKER_TO_KR.get(ticker, ticker))


if __name__ == "__main__":
    # 매핑 테스트
    test_names = ["유바이오로직스", "반도체", "아시아경제", "삼성전자", "모르는회사"]
    print("=== 회사명 → 티커 매핑 테스트 ===")
    for name in test_names:
        t = name_to_ticker(name)
        print(f"  {name:20s} → {t}")
