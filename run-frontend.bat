@echo off
REM Starts the React + Vite dev server at http://localhost:5173.
REM The backend must be running too: the UI sends /api calls to it.
cd /d "%~dp0frontend"
if not exist node_modules call npm install
call npm run dev
