@echo off
title JARVIS AI Assistant
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo Starting JARVIS AI Assistant...
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" main.py %*
) else (
    call .venv\Scripts\activate.bat
    python main.py %*
)
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo JARVIS exited with code %ERRORLEVEL%.
    pause
)
