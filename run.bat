@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
start "" http://localhost:8000
python -m uvicorn app.main:app --port 8000
