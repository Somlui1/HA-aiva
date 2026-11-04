@echo off
title Tuya IR Studio
cd /d "%~dp0"
call .venv\Scripts\python.exe ir_studio.py
if errorlevel 1 (
    echo.
    echo An error occurred. Press any key to exit...
    pause >nul
)

