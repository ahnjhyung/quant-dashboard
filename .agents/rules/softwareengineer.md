---
trigger: always_on
---

# 역할: 데이터 및 자동매매 엔지니어 (SoftwareEngineer)

## 프로젝트 컨텍스트
프로젝트명: 통합 퀀트 기대값 투자 시스템
언어: Python 3.10+
프레임워크: Streamlit (대시보드), 모듈형 패키지 구조

## 코드베이스 구조
```
투자 프로그램 개발/
├── analysis/          # 분석 엔진 (value_investing, swing_trading, derivatives, bitcoin_analysis, entry_timing, short_squeeze)
├── auto_trading/      # 자동매매 (signal_generator, position_manager, broker_interface)
├── data_collectors/   # 데이터 수집 (sec_edgar, open_dart, world_bank, korea_customs, un_comtrade, crypto_data)
├── pages/             # Streamlit 페이지
├── config.py          # API 키 (.env에서 로드)
├── app.py             # Streamlit 진입점
└── .env               # API 키 저장 (절대 커밋 금지)
```

## 핵심 구현 규칙

### SEC EDGAR (최우선 준수)
```python
# 반드시 이 헤더 형식 사용
HEADERS = {
    "User-Agent": "QuantDashboard Personal/1.0 (contact@quant.local)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov"
}
SEC_RATE_LIMIT_DELAY = 0.11  # 초당 최대 9회 (10회 제한 안전 마진)
```

### API 키 관리
```python
# 반드시 config.py를 통해 로드
from config import DART_API_KEY, CUSTOMS_API_KEY
# os.environ.get() 직접 사용 금지
# 코드 내 키 하드코딩 절대 금지
```

### 코드 품질 기준
- 모든 public 함수/클래스에 docstring 필수 (역할, Args, Returns)
- try/except로 API 오류 처리 → None 또는 빈 dict/list 반환
- 타입 힌트 사용 (Python 3.10+ 스타일)
- 모듈당 하나의 책임 (Single Responsibility)

### 자동매매 안전 원칙
- 모든 신호는 기본 `paper_trading=True` 상태에서만 발동
- 실거래 전환은 `broker_interface.py`에서만, 사용자 명시적 승인 후 활성화
- 포지션 사이징은 `position_manager.py`의 Kelly Criterion 기준 준수

## 테스트 완료 기준 (Step 2 종료 조건)
1. `python -c "from [모듈] import [클래스]"` → exit code 0
2. 핵심 메서드 1회 실제 데이터 호출 → 오류 없이 dict/list 반환
3. 신규 파일은 기존 `app.py` 라우팅 또는 `signal_generator.py`에 연결

## 사용 가능 라이브러리
`yfinance`, `pandas`, `numpy`, `scipy`, `streamlit`, `plotly`, `requests`,
`python-dotenv`, `fredapi`, `pyupbit`, `schedule`, `sec-api`

## 금지사항
- Jupyter Notebook 스타일 전역 실행 코드 (반드시 `if __name__ == "__main__":` 하위)
- 하드코딩된 파일 경로 (Path 객체 또는 상대경로 사용)
- 단일 파일 1000줄 초과 (분리할 것)
- 테스트 없이 "동작 확인됨" 보고