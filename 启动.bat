@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo ============================================================
echo  NLPilot 启动
echo ============================================================
echo.
echo  第一次使用、或改过前端代码，请先构建一次：
echo      cd frontend  ^&^&  npm run build
echo.
echo  浏览器会自动打开；停止请按 Ctrl+C
echo.

".venv\Scripts\python.exe" run.py

echo.
echo  服务已停止。
pause
