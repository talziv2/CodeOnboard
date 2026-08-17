@echo off
setlocal
cd /d "%~dp0"

rem Objective-first planner (B3). Set to 0 to use the pre-B3 planner.
set "CODEONBOARD_CURRICULUM=1"

rem Gap model (learning-graph.md §11 OQ-4, decided 2026-08-17). DEVELOPMENT
rem ONLY — `flags.gaps_enabled()` still defaults to 0, so the shipped default
rem and the test suite are unaffected.
rem
rem THIS IS NOT DATA COLLECTION ONLY. It also changes runtime adaptation: the
rem Grader derives the scalar `gap_kind` from the gaps it finds, and that scalar
rem selects the intervention (hint / re-teach / prerequisite / follow-up). The
rem measured direction is an improvement — gap_kind agreement 47-48/48 against a
rem baseline of 45, missing_prerequisite 4/6 -> 6/6 — but a flag-on session can
rem receive a different intervention than the same session flag-off.
rem
rem Gaps are collected but NOT shown to the learner: nothing can close one until
rem gap-model M6 ships verification, so a displayed list would only ever grow.
set "CODEONBOARD_GAPS=1"

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
echo   Backend:  http://localhost:8000  (CODEONBOARD_CURRICULUM=%CODEONBOARD_CURRICULUM%)
echo   Frontend: http://localhost:3000
