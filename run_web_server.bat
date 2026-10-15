@echo off
title ZTE SMS Live Messenger
echo Starting ZTE SMS Live Messenger with Auto-sync every 5 seconds...
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0main.py" %*
) else (
    python "%~dp0main.py" %*
)
pause
