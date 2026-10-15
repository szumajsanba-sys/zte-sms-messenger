@echo off
title ZTE SMS Desktop GUI
echo Starting ZTE SMS Keeper & Messenger Desktop GUI...
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0main.py" --gui %*
) else (
    python "%~dp0main.py" --gui %*
)
pause
