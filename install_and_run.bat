@echo off
chcp 65001 >nul
echo ========================================================
echo 🚀 퀀트 주식 스크리닝 대시보드 자동 설치 및 실행
echo ========================================================
echo.
echo [1/2] 필수 파이썬 라이브러리 설치/업데이트 중입니다...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
echo.
echo [2/2] 리소스 설치 완료! 대시보드를 실행합니다...
echo 최초 실행 시 브라우저가 열릴 때까지 몇 초간 소요될 수 있습니다.
echo.
streamlit run app.py
pause