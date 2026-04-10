@echo off
REM =============================================================================
REM  start.bat — Insurance PAS Live Monitor · Launcher (Windows)
REM
REM  Usage:
REM    start.bat               Manual query TUI  (no Docker needed)
REM    start.bat --live        Split-screen live monitor (Docker + MySQL)
REM    start.bat --live --no-tui   Console-only live demo
REM    start.bat --api         REST API on http://localhost:8000
REM =============================================================================
setlocal EnableDelayedExpansion

REM ── Parse args ────────────────────────────────────────────────────────────────
set MODE=manual
set NO_TUI=0

for %%A in (%*) do (
    if "%%A"=="--live"   set MODE=live
    if "%%A"=="--api"    set MODE=api
    if "%%A"=="--no-tui" set NO_TUI=1
    if "%%A"=="--help"   goto :show_help
    if "%%A"=="-h"       goto :show_help
)
goto :start

:show_help
echo.
echo  Insurance PAS ^· Live Monitor
echo.
echo    start.bat                 Manual query TUI (no Docker)
echo    start.bat --live          Split-screen live monitor
echo    start.bat --live --no-tui Console-only live demo
echo    start.bat --api           REST API on http://localhost:8000
echo.
exit /b 0

:start

REM ── Activate venv ─────────────────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo   X  venv not found — run setup.bat first
    pause & exit /b 1
)
call venv\Scripts\activate.bat

REM ── Banner ────────────────────────────────────────────────────────────────────
echo.
echo  Insurance PAS ^· Live Monitor
echo  ==========================================

REM =============================================================================
REM  MODE: manual
REM =============================================================================
if "!MODE!"=="manual" (
    echo    Mode: Manual Query TUI
    echo    Ask about SQL performance, explore cases, detect anomalies
    echo.
    python cli\tui.py
    exit /b 0
)

REM =============================================================================
REM  MODE: api
REM =============================================================================
if "!MODE!"=="api" (
    echo    Mode: REST API
    echo    Docs: http://localhost:8000/docs
    echo.
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
    exit /b 0
)

REM =============================================================================
REM  MODE: live — split-screen live monitor (requires Docker + MySQL)
REM =============================================================================
echo    Mode: Live Monitor ^(PAS + AI split-screen^)
echo.

REM ── Docker check ─────────────────────────────────────────────────────────────
docker --version >nul 2>&1
if errorlevel 1 (
    echo   X  Docker not found.
    echo      Install Docker Desktop: https://www.docker.com/products/docker-desktop
    pause & exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo   X  Docker is not running. Start Docker Desktop and retry.
    pause & exit /b 1
)

REM ── Start MySQL ───────────────────────────────────────────────────────────────
echo   Starting MySQL ^(Docker^)...

docker compose up -d >nul 2>&1
if errorlevel 1 (
    docker-compose up -d
    if errorlevel 1 (
        echo   X  docker-compose failed. Check docker-compose.yml exists.
        pause & exit /b 1
    )
)

echo   OK  MySQL container started ^(port 3307^)

REM ── Wait for MySQL ────────────────────────────────────────────────────────────
echo   Waiting for MySQL to be ready...
echo      ^(First run downloads + imports 4.1M rows -- can take 5-10 minutes^)

python -c "
import sys, time
try:
    import mysql.connector
except ImportError:
    print('  X  mysql-connector-python not installed -- run setup.bat')
    sys.exit(1)

MAX_WAIT = 600
INTERVAL = 5
elapsed = 0
last_error = ''

while elapsed < MAX_WAIT:
    try:
        cnx = mysql.connector.connect(
            host='localhost', port=3307,
            user='monitor', password='monitor_pw',
            database='employees', connection_timeout=5,
        )
        cur = cnx.cursor()
        cur.execute('SELECT COUNT(*) FROM employees')
        count = cur.fetchone()[0]
        cur.close()
        cnx.close()
        if count > 0:
            print(f'\n  OK  MySQL ready -- employees table has {count:,} rows')
            sys.exit(0)
        last_error = 'employees table empty'
    except Exception as exc:
        last_error = str(exc)
    mins = elapsed // 60
    secs = elapsed % 60
    sys.stdout.write(f'\r  Waiting... {mins}m{secs:02d}s')
    sys.stdout.flush()
    time.sleep(INTERVAL)
    elapsed += INTERVAL

print(f'\n  X  MySQL not ready after {MAX_WAIT//60} minutes')
print(f'     Last error: {last_error}')
print('     Check logs: docker compose logs mysql')
sys.exit(1)
"

if errorlevel 1 (
    pause & exit /b 1
)

echo.

REM ── Launch ────────────────────────────────────────────────────────────────────
if "!NO_TUI!"=="1" (
    echo   Launching console demo...
    echo.
    python demo_live.py --no-tui
) else (
    echo   Launching split-screen TUI...
    echo   SPACE = Pause/Resume   Q = Quit
    echo.
    python demo_live.py
)
