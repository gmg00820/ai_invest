@echo off
chcp 65001 >nul
echo ========================================================
echo 🚀 퀀트 주식 스크리닝 대시보드 자동 실행 (64비트 가상환경)
echo ========================================================
echo.
echo 가상환경 검사 및 실행을 준비 중입니다...
if not exist "%~dp0.venv" (
    echo [오류] 64비트 가상환경(.venv)이 존재하지 않습니다.
    pause
    exit /b
)
echo.
echo [실행] 대시보드를 실행합니다...
echo 최초 실행 시 브라우저가 열릴 때까지 몇 초간 소요될 수 있습니다.
echo.
"%~dp0.venv\Scripts\streamlit.exe" run "%~dp0app.py"
pause