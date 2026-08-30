@echo off
setlocal
cd /d "%~dp0"

rem Opens both servers in their own windows. A convenience — the supported path
rem is the two commands in RUN.md, and this runs exactly those.
rem
rem NO FLAGS ARE SET HERE, deliberately. This used to force
rem CODEONBOARD_CURRICULUM=1 and CODEONBOARD_GAPS=1, so anyone who launched the
rem project this way got a different planner and a different remediation path
rem than the documented commands give, with nothing on screen to say so. Put
rem either in `.env` if you want it; see `.env.example`.

netstat -ano | findstr "LISTENING" | findstr ":8000 " >nul
if %errorlevel%==0 (
  echo Backend already running on port 8000 - skipping.
) else (
  start "CodeOnboard backend" cmd /k uv run python -m uvicorn backend.api:app --port 8000 --reload
)

netstat -ano | findstr "LISTENING" | findstr ":3000 " >nul
if %errorlevel%==0 (
  echo Frontend already running on port 3000 - skipping.
) else (
  start "CodeOnboard frontend" cmd /k "cd /d frontend && npm run dev"
)

echo.
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000
