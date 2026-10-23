@echo off
title MARK-LVI AI Assistant
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo Starting MARK-LVI...
call .venv\Scripts\activate.bat
python main.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo MARK-LVI exited with code %ERRORLEVEL%.
    pause
)
