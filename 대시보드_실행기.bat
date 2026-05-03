@echo off
title AGA Quant Dashboard Launcher
echo ==================================================
echo   AGA Premium Quant Dashboard를 시작합니다.
echo ==================================================
echo.
echo [1/3] 시스템 보안 인증서(SSL) 상태를 확인하고 복구합니다...
python scripts\fix_ssl_certs.py

:: Get certifi path and set environment variables
for /f "delims=" %%i in ('python -c "import certifi; print(certifi.where())"') do set "CERT_PATH=%%i"
set "SSL_CERT_FILE=%CERT_PATH%"
set "REQUESTS_CA_BUNDLE=%CERT_PATH%"

echo.
echo [2/3] 필요한 라이브러리 설치 확인...
pip install streamlit plotly pandas numpy yfinance requests python-dotenv

echo.
echo [3/3] 스트림릿 대시보드를 실행합니다...
streamlit run app.py

pause
