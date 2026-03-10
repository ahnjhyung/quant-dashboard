---
description: 새로운 퀀트 전략 또는 기능 개발 시 전략설계→구현→보안감사→PM보고까지 전체 파이프라인
---

# /basicprocess — 기본 개발 파이프라인

**사용 시점**: 새로운 분석 모듈, 데이터 수집기, 자동매매 신호, 대시보드 페이지를 개발할 때.
**출력물 흐름**: `tech_spec` → `Python 모듈` → `Security Report` → `PM 브리핑`

---

## Step 1 — 전략 설계 [quantanalyst.md]

**담당**: QuantAnalyst
**목표**: EV 기반 투자 전략을 설계하고 개발자가 즉시 코딩 가능한 tech_spec 작성

**수행 내용**:
- 현재 시장 상황 및 기존 모듈 현황 파악
- EV > 0 조건을 충족하는 전략 선택 (리픽싱 CB / 숏스퀴즈 / 가치투자 / 스윙 / 파생상품 / BTC 등)
- tech_spec 작성:
  - 변수명 (Python에서 실제 사용될 이름)
  - 수식 (EV 계산식 포함)
  - 데이터 소스 (어떤 API의 어떤 필드)
  - 진입/청산 기준
  - 엣지 케이스 및 예상 리스크

**승인 기준** (PM이 다음을 확인해야 Step 2 진행):
- [ ] EV 수식이 명시되어 있는가?
- [ ] 변수명과 API 소스가 명확한가?
- [ ] 엣지 케이스가 언급되어 있는가?

---

## Step 2 — Python 구현 [softwareengineer.md]

**담당**: SoftwareEngineer
**목표**: tech_spec을 Python 모듈로 완전 구현

**수행 내용**:
- 올바른 디렉토리에 파일 생성:
  - 분석 로직 → `analysis/`
  - 데이터 수집 → `data_collectors/`
  - 자동매매 신호 → `auto_trading/`
  - 대시보드 페이지 → `pages/`
- SEC EDGAR 사용 시 `HEADERS` 형식 및 `rate_limit=0.11s` 반드시 준수
- 모든 API 키는 `config.py` 경유 (직접 하드코딩 절대 금지)
- `auto_trading` 신호는 `paper_trading=True` 기본값 유지
- 신규 파일은 `analysis/__init__.py` 및 `app.py` 라우팅에 연결
- 코드 저장 후 터미널 테스트:
  ```
  python -c "from [모듈] import [클래스]"
  ```

**승인 기준** (PM이 다음을 확인해야 Step 3 진행):
- [ ] import 테스트 exit code 0
- [ ] 실제 데이터 1건 호출 성공
- [ ] app.py 또는 signal_generator.py에 연결됨

---

## Step 3 — 보안 감사 [securityauditor.md]

**담당**: SecurityAuditor
**목표**: Step 2 생성 파일의 보안/로직 취약점 전수 조사 및 직접 수정

**수행 내용**:
- 생성된 모든 파일 코드 전체 라인 검토
- 4단계 위험 등급으로 취약점 분류:
  - **[CRITICAL]**: API 키 하드코딩, 실거래 기본값, EV 부호 오류 → 즉시 수정
  - **[HIGH]**: EV 수식 오류, Kelly 분모 0, NaN 전파 → 당일 수정
  - **[MEDIUM]**: API 응답 검증 미흡, 예외처리 누락 → 다음 사이클 전 수정
  - **[LOW]**: 불필요한 import, rate limit 누락 → 개선 권고
- 발견된 취약점은 **보고만 하지 말고 파일에 직접 반영**

**승인 기준** (PM이 다음을 확인해야 Step 4 진행):
- [ ] CRITICAL 0건
- [ ] HIGH 0건
- [ ] 모든 수정 사항이 코드에 반영됨

---

## Step 4 — PM 최종 보고 [projectmanager.md]

**담당**: ProjectManager
**목표**: 전체 사이클 검토 후 재형님께 간결하게 브리핑

**보고 형식**:
```
## [기능명] 완료 보고

**무엇을**: [한 줄 요약]
**핵심 공식**: [EV 또는 핵심 수식 1~2줄]
**보안**: CRITICAL 0건, HIGH 0건, MEDIUM N건 수정 완료
**다음 우선순위**: [다음 작업 1가지]
```

**체크**:
- [ ] 각 Step의 승인 기준이 모두 충족되었는가?
- [ ] EV 계산 로직이 코드에 올바르게 반영되어 있는가?
- [ ] 다음 로드맵 우선순위가 명확히 제시되어 있는가?