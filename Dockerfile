# Python 3.10 slim 이미지를 기반으로 사용합니다 (가볍고 빠름)
FROM python:3.10-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 의존성 패키지 설치 (빌드 도구 등)
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 패키지 설치 목록 복사
COPY requirements.txt .

# 파이썬 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 전체 복사 (.dockerignore에 명시된 파일(예: .env) 제외됨)
COPY . .

# 컨테이너 시작 시 실행될 기본 명령어 (통합 퀀트 엔진 실행)
CMD ["python", "quant_engine.py"]
