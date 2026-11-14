@echo off
cd /d "%~dp0\.."
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 exit /b 1
cd backend
..\.venv\Scripts\python.exe -m protolab.web --port 8877
pause
