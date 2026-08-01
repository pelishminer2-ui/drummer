@echo off
setlocal
cd /d "%~dp0"
python drummer_app.py
if errorlevel 1 (
  echo.
  echo Python 3 is required. Install from https://www.python.org/downloads/
  pause
)
