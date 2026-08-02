@echo off
cd /d "%~dp0source"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" drummer_app.py
) else (
    echo GPU venv not found. Run source\install-gpu.ps1 first.
    python drummer_app.py
)
