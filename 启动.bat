@echo off
chcp 65001 >nul
echo ========================================
echo    个人知识库智能助手 - 启动中...
echo ========================================
echo.
cd /d "%~dp0"
python -m uvicorn server:app --reload --port 8000
pause
