@echo off
REM Runs the email pipeline. By default it drains the inbox once and exits.
REM   run-pipeline.bat                 (process all waiting emails, then stop)
REM   run-pipeline.bat --limit 20       (process at most 20)
REM Pass no args for a one-shot drain; add nothing to poll forever use: run-pipeline.bat loop
cd /d "%~dp0"
if "%~1"=="loop" (
    ".venv\Scripts\python.exe" scripts\run_pipeline.py
) else (
    ".venv\Scripts\python.exe" scripts\run_pipeline.py --once %*
)
