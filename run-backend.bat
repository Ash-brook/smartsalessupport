@echo off
REM Starts the FastAPI backend at http://localhost:8000  (docs at /docs).
cd /d "%~dp0"
".venv\Scripts\python.exe" -m uvicorn backend.main:app --reload --port 8000
