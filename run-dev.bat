@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ===========================================================================
rem CodeOnboard - Windows development launcher.
rem
rem Starts the FastAPI backend and the Next.js frontend, each in its own window,
rem and does not claim success until it has PROVED both are answering.
rem
rem THE BUG THIS EXISTS TO PREVENT. The previous version asked netstat whether
rem anything held ports 8000 and 3000, started whatever was missing, and then
rem printed "Backend: http://localhost:8000" unconditionally. Both halves of
rem that are wrong:
rem
rem   - A held port is not a healthy service. Anything at all on 8000 - a stale
rem     process, an unrelated dev server - was read as "backend already running"
rem     and the real backend was never started.
rem   - Nothing was ever verified after starting. A backend that crashed two
rem     seconds in left the launcher reporting a success it had not checked.
rem
rem Either way the learner got a running frontend, no backend, and a launcher
rem that said everything was fine. In the browser that surfaced as
rem "Internal Server Error" under the password field, because the Next.js
rem /api/* rewrite answers an unreachable FastAPI with its own 500.
rem
rem So every check here is an HTTP request to the service itself, never a port
rem count, and the summary at the bottom reports only what was observed.
rem
rem NO FLAGS ARE SET HERE, deliberately. This used to force
rem CODEONBOARD_CURRICULUM=1 and CODEONBOARD_GAPS=1, so anyone who launched the
rem project this way got a different planner and a different remediation path
rem than the documented commands give, with nothing on screen to say so.
rem
rem Both of those flags have since been removed - the planner and the gap model
rem they selected are simply how the system works now - which settles that
rem divergence rather than papering over it. The rule stands for whatever comes
rem next: a launcher that quietly sets a flag makes the app it starts different
rem from the app the documentation describes.
rem
rem THE TUTOR NEEDS NOTHING SET, and that is the point of its default rather
rem than an accident. CODEONBOARD_TUTOR and NEXT_PUBLIC_CODEONBOARD_TUTOR both
rem default ON and are read as "not explicitly 0", so a fresh clone launched
rem from here starts the COMPLETE application. They used to default off, which
rem meant this launcher reported both services UP and handed over an app whose
rem Tutor was compiled out of the bundle - a working product that looked like a
rem missing feature, diagnosable only by knowing to go looking for two
rem variables. Setting them here instead would have rebuilt the original bug in
rem a different place: the feature would work when launched THIS way and vanish
rem for anyone following the two-terminal instructions.
rem ===========================================================================

rem --- Work from this script's own folder, however it was launched -----------
rem Double-clicking starts cmd in C:\Windows\System32, so without this nothing
rem below resolves. The trailing backslash that %~dp0 always carries is stripped
rem because "%ROOT%\" inside a quoted argument escapes the closing quote, which
rem is how launchers break on paths containing spaces.
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "EXITCODE=0"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3000"
set "BACKEND_PROBE=http://127.0.0.1:%BACKEND_PORT%/health"
set "FRONTEND_PROBE=http://127.0.0.1:%FRONTEND_PORT%/login"
set "APP_URL=http://localhost:%FRONTEND_PORT%"

rem Seconds to wait for each service to answer after starting it. The backend
rem imports tree-sitter and LangGraph; the frontend compiles the route on first
rem request. Both are slow on a cold machine, and a launcher that gives up too
rem early reports a failure that was only ever a delay.
rem Overridable, because "slow machine" and "genuinely broken" are the same
rem observation with a different deadline, and only the person at the keyboard
rem knows which one they are on.
if not defined CODEONBOARD_BACKEND_WAIT set "CODEONBOARD_BACKEND_WAIT=90"
if not defined CODEONBOARD_FRONTEND_WAIT set "CODEONBOARD_FRONTEND_WAIT=150"
set "BACKEND_WAIT=%CODEONBOARD_BACKEND_WAIT%"
set "FRONTEND_WAIT=%CODEONBOARD_FRONTEND_WAIT%"

rem Pause before closing only when there would otherwise be nobody to read the
rem window. Launched from an open terminal the output stays on screen and a
rem pause is just an extra keypress; double-clicked, the window closes instantly
rem and takes every diagnostic with it.
set "DOUBLECLICKED="
set "CMDLINE=%cmdcmdline%"
echo !CMDLINE! | find /i "%~nx0" >nul 2>&1 && set "DOUBLECLICKED=1"

echo.
echo   CodeOnboard - starting the development servers
echo   ---------------------------------------------

cd /d "%ROOT%" 2>nul
if errorlevel 1 (
  echo.
  echo   [X] Could not open the project folder:
  echo       %ROOT%
  set "EXITCODE=1"
  goto :finish
)

rem --- Preflight: fail with a fixable message, not a stack trace -------------
rem Each of these otherwise produces an instant, cryptic crash inside a child
rem window, which the launcher could only report as "did not come up in time".
if not exist "%ROOT%\backend\api.py" (
  echo.
  echo   [X] This does not look like the CodeOnboard project folder:
  echo       %ROOT%
  echo       Expected to find backend\api.py beside this script.
  set "EXITCODE=1"
  goto :finish
)
if not exist "%ROOT%\frontend\package.json" (
  echo.
  echo   [X] frontend\package.json is missing from:
  echo       %ROOT%
  echo       The checkout looks incomplete.
  set "EXITCODE=1"
  goto :finish
)

where uv >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [X] 'uv' is not on PATH, so the backend cannot start.
  echo       Install it from https://docs.astral.sh/uv/ then reopen this window.
  set "EXITCODE=1"
  goto :finish
)
where npm >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [X] 'npm' is not on PATH, so the frontend cannot start.
  echo       Install Node.js from https://nodejs.org/ then reopen this window.
  set "EXITCODE=1"
  goto :finish
)
where curl.exe >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [X] curl.exe was not found. This script uses it to check that each
  echo       service is really answering, and without it those checks would be
  echo       guesses - which is the exact failure this launcher was rewritten
  echo       to stop making. curl.exe ships in System32 on Windows 10 1803+.
  set "EXITCODE=1"
  goto :finish
)

rem Node dependencies are the one prerequisite this script can satisfy itself,
rem and 'npm run dev' without them fails in a child window in under a second.
if not exist "%ROOT%\frontend\node_modules" (
  echo.
  echo   Frontend dependencies are not installed yet. Running 'npm install' -
  echo   this happens once and can take a few minutes.
  echo.
  pushd "%ROOT%\frontend"
  call npm install
  set "NPM_FAILED=!errorlevel!"
  popd
  if not "!NPM_FAILED!"=="0" (
    echo.
    echo   [X] 'npm install' failed with code !NPM_FAILED!. Its output says why.
    set "EXITCODE=1"
    goto :finish
  )
)

rem --- Prove uv can actually produce an interpreter --------------------------
rem Without this the launcher's only evidence of a broken Python environment is
rem ninety seconds of silence followed by "see its window" - and the window in
rem question holds a one-line uv error that has scrolled up behind a prompt. The
rem observed case was
rem
rem   No Python at '...\uv\python\cpython-3.11.15-...\python.exe'
rem
rem which kills uvicorn instantly, long before anything could bind a port. This
rem also warms uv's cache and syncs the project, so the real start is quicker.
rem Only when we are actually going to start it. If the backend is already up,
rem a broken uv is irrelevant to this run, and failing here would report a dead
rem app while the learner is looking at a working one.
call :port_owner %BACKEND_PORT%
if not defined PORT_PID (
  echo.
  <nul set /p "=- Checking the Python environment "
  uv run python -c "pass" >nul 2>&1
  if !errorlevel! neq 0 goto :uv_broken
  echo - ok.
)

rem --- Bring up each service -------------------------------------------------
echo.
call :ensure BACKEND  "Backend"  %BACKEND_PORT%  "%BACKEND_PROBE%"  %BACKEND_WAIT%
call :ensure FRONTEND "Frontend" %FRONTEND_PORT% "%FRONTEND_PROBE%" %FRONTEND_WAIT%

rem --- Final status ----------------------------------------------------------
rem Reported from what the probes actually observed. A service is only ever
rem called UP here because it answered an HTTP request.
rem FAILED means "we started it and it never answered", which is the only case
rem with a child window worth reading. BLOCKED started nothing.
set "ANY_FAILED="
if "!BACKEND_STATUS!"=="FAILED" set "ANY_FAILED=1"
if "!FRONTEND_STATUS!"=="FAILED" set "ANY_FAILED=1"

echo.
echo   ---------------------------------------------
call :report "Backend " %BACKEND_PORT%  "!BACKEND_STATUS!"  "!BACKEND_NOTE!"
call :report "Frontend" %FRONTEND_PORT% "!FRONTEND_STATUS!" "!FRONTEND_NOTE!"
echo   ---------------------------------------------
echo.

if "!BACKEND_STATUS!"=="UP" if "!FRONTEND_STATUS!"=="UP" (
  echo   Both services are up, with the Tutor enabled. Open the app at:
  echo.
  echo       %APP_URL%
  echo.
  echo   The Tutor is the CHAT control beside "Show source" inside a lesson.
  echo   It needs no configuration. To turn it off, set CODEONBOARD_TUTOR=0
  echo   in .env AND NEXT_PUBLIC_CODEONBOARD_TUTOR=0 in frontend\.env.local,
  echo   then run this again - the second is read at build time, so a reload
  echo   is not enough.
  echo.
  goto :finish
)

set "EXITCODE=1"
echo   [X] NOT READY - the app will not work correctly yet.
echo.
if not "!BACKEND_STATUS!"=="UP" (
  echo       The frontend reaches the backend through its /api/* proxy, so with
  echo       the backend down every page that loads data fails, and signing in
  echo       reports a server error rather than a wrong password.
  echo.
)
if defined ANY_FAILED (
  echo       A window titled "CodeOnboard backend" or "CodeOnboard frontend" is
  echo       still open with the error in it - that is why it was not closed.
  echo.
)
goto :finish


:uv_broken
echo - FAILED.
echo.
echo   [X] 'uv run' could not start Python, so the backend cannot run at all.
echo       Nothing was started. uv reports:
echo.
rem Re-run without swallowing the output: this is the only place uv's own words
rem reach the person reading, and they name the missing interpreter exactly.
uv run python -c "pass"
echo.
echo       Usually the interpreter this project's .venv points at has gone -
echo       moved, cleaned up, or half-installed. Rebuild the environment with:
echo.
echo           uv sync
echo.
echo       If that does not fix it, delete the .venv folder and run 'uv sync'
echo       again. 'uv python list' shows which interpreters uv can still see.
echo.
set "EXITCODE=1"
goto :finish


rem ===========================================================================
rem :ensure  KIND  Label  Port  ProbeUrl  WaitSeconds
rem
rem Sets <KIND>_STATUS to UP, BLOCKED or FAILED, and <KIND>_NOTE to a phrase
rem saying which.
rem ===========================================================================
:ensure
set "KIND=%~1"
set "LABEL=%~2"
set "PORT=%~3"
set "URL=%~4"
set "LIMIT=%~5"

rem Is anything holding the port? Asked first, because whether a silent port
rem means "still warming up" or "somebody else's process" depends on the answer.
call :port_owner %PORT%

if defined PORT_PID (
  rem Something is there. The only question that matters is whether it is OURS,
  rem and the only honest way to ask is to make a request and see who answers.
  rem The timeout is generous because a frontend that is already running but
  rem cold still has to compile the route before it can reply, and calling that
  rem "an unrelated process" would be exactly the old script's mistake.
  <nul set /p "=- %LABEL%: port %PORT% is in use, checking whether it is CodeOnboard "
  call :probe "%URL%" 20
  if not "!HTTP_CODE!"=="000" (
    echo - yes.
    set "%KIND%_STATUS=UP"
    set "%KIND%_NOTE=already running, reused"
    goto :eof
  )
  echo - no.
  call :proc_name !PORT_PID!
  set "%KIND%_STATUS=BLOCKED"
  set "%KIND%_NOTE=port held by !PROC_NAME! ^(PID !PORT_PID!^)"
  echo     Port %PORT% is held by !PROC_NAME! ^(PID !PORT_PID!^), which is not
  echo     the CodeOnboard %LABEL%. Nothing was started, because it could not
  echo     have bound the port anyway. Free the port, then run this again.
  goto :eof
)

rem Port is free: start the service, then prove it came up.
<nul set /p "=- %LABEL%: starting "
call :start_%KIND%

set /a WAITED=0
:ensure_wait
call :probe "%URL%" 3
if not "!HTTP_CODE!"=="000" (
  echo  ready.
  set "%KIND%_STATUS=UP"
  set "%KIND%_NOTE=started by this script"
  goto :eof
)
if !WAITED! GEQ %LIMIT% (
  echo  FAILED.
  set "%KIND%_STATUS=FAILED"
  set "%KIND%_NOTE=no answer within %LIMIT%s - see its window"
  goto :eof
)
<nul set /p "=."
rem ping is the sleep that is always present and never needs stdin, unlike
rem 'timeout', which errors out whenever this script's input is redirected.
ping -n 2 127.0.0.1 >nul 2>&1
set /a WAITED+=1
goto :ensure_wait


rem --- The two start commands ------------------------------------------------
rem Both inherit this window's working directory, which the cd above pinned to
rem the project root, so neither has to quote a path - and a project path
rem containing spaces cannot break them. 'cmd /k' is deliberate: the window
rem stays open when the process dies, so the traceback is still on screen when
rem the launcher reports the failure.
:start_BACKEND
start "CodeOnboard backend" cmd /k uv run python -m uvicorn backend.api:app --port %BACKEND_PORT% --reload
goto :eof

:start_FRONTEND
start "CodeOnboard frontend" cmd /k "cd /d frontend && npm run dev"
goto :eof


rem ===========================================================================
rem :probe  Url  TimeoutSeconds  ->  HTTP_CODE  ("000" = nothing answered)
rem
rem curl reports 000 when it could not connect at all, and the real status
rem otherwise. Any status is proof that a server answered. The backend probe
rem asks for /health, which exists to answer exactly this question and which an
rem unrelated process holding port 8000 would not serve. Both it and the
rem frontend's /login are reachable without a session, so neither probe can be
rem defeated by not being signed in.
rem ===========================================================================
:probe
set "HTTP_CODE=000"
for /f "usebackq delims=" %%C in (`curl.exe -s -o nul --max-time %~2 -w "%%{http_code}" "%~1" 2^>nul`) do set "HTTP_CODE=%%C"
if "!HTTP_CODE!"=="" set "HTTP_CODE=000"
goto :eof


rem ===========================================================================
rem :port_owner  Port  ->  PORT_PID  (left undefined when nothing is listening)
rem ===========================================================================
:port_owner
set "PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano -p TCP ^| findstr /r /c:":%~1 .*LISTENING"') do (
  if not defined PORT_PID set "PORT_PID=%%P"
)
goto :eof


rem ===========================================================================
rem :proc_name  Pid  ->  PROC_NAME
rem ===========================================================================
:proc_name
set "PROC_NAME=an unknown process"
for /f "usebackq tokens=1 delims=," %%N in (`tasklist /nh /fo csv /fi "PID eq %~1" 2^>nul`) do (
  set "PROC_NAME=%%~N"
)
goto :eof


rem ===========================================================================
rem :report  Label  Port  Status  Note
rem ===========================================================================
:report
rem Pad the status to a fixed width so the notes line up whether the word is
rem UP, FAILED or BLOCKED.
set "ST=%~3        "
set "ST=!ST:~0,9!"
echo   %~1  http://localhost:%~2   !ST!- %~4
goto :eof


:finish
if defined DOUBLECLICKED (
  echo   Press any key to close this window.
  pause >nul
) else if not "%EXITCODE%"=="0" (
  echo   Press any key to continue.
  pause >nul
)
endlocal & exit /b %EXITCODE%
