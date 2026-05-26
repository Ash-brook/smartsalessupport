@echo off
REM Seeds the SQLite database with synthetic customers, orders, and emails.
REM Usage: seed.bat                 (defaults: 50 customers, 3 orders each, 200 emails)
REM        seed.bat --emails 50     (override any flag)
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\seed.py %*
