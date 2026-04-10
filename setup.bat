@echo off
REM =============================================================================
REM  setup.bat — Insurance PAS Live Monitor · One-time setup (Windows)
REM  Run this in Command Prompt or PowerShell
REM =============================================================================
setlocal EnableDelayedExpansion

echo.
echo  Insurance PAS ^· Live Monitor ^— Setup
echo  ==========================================
echo.

REM =============================================================================
REM  STEP 1 — Python 3.12+
REM =============================================================================
echo [1/5] Checking Python...

python --version >nul 2>&1
if errorlevel 1 (
    echo   X  Python not found.
    echo      Download from: https://www.python.org/downloads/
    echo      Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PY_VER=%%V
for /f "tokens=1,2 delims=." %%A in ("!PY_VER!") do (
    set PY_MAJOR=%%A
    set PY_MINOR=%%B
)

if !PY_MAJOR! LSS 3 (
    echo   X  Python 3.12+ required. Found: !PY_VER!
    pause & exit /b 1
)
if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 12 (
    echo   X  Python 3.12+ required. Found: !PY_VER!
    pause & exit /b 1
)

echo   OK  Python !PY_VER!

REM =============================================================================
REM  STEP 2 — Virtual environment
REM =============================================================================
echo.
echo [2/5] Virtual environment...

if not exist "venv" (
    echo     Creating venv...
    python -m venv venv
    if errorlevel 1 (
        echo   X  Failed to create venv
        pause & exit /b 1
    )
)

call venv\Scripts\activate.bat
if errorlevel 1 (
    echo   X  Failed to activate venv
    echo      Delete the venv\ folder and rerun setup.bat
    pause & exit /b 1
)

echo   OK  venv activated

REM =============================================================================
REM  STEP 3 — Dependencies
REM =============================================================================
echo.
echo [3/5] Installing dependencies...

python -m pip install --upgrade pip --quiet
if errorlevel 1 ( echo   X  pip upgrade failed & pause & exit /b 1 )

python -m pip install -r requirements.txt --quiet
if errorlevel 1 ( echo   X  pip install failed & pause & exit /b 1 )

echo   OK  All packages installed

REM =============================================================================
REM  STEP 4 — Environment file
REM =============================================================================
echo.
echo [4/5] Environment (.env)...

if not exist ".env" (
    copy .env.example .env >nul
    echo   OK  .env created from .env.example
    echo   !   Edit .env to add your LLM API key (optional — works offline too)
) else (
    echo   OK  .env already exists
)

REM =============================================================================
REM  STEP 5 — Docker check
REM =============================================================================
echo.
echo [5/5] Docker (for live MySQL demo)...

docker --version >nul 2>&1
if errorlevel 1 (
    echo   !   Docker not found.
    echo       Install Docker Desktop: https://www.docker.com/products/docker-desktop
    echo       Docker is only needed for: start.bat --live
) else (
    docker info >nul 2>&1
    if errorlevel 1 (
        echo   !   Docker is installed but not running. Start Docker Desktop.
    ) else (
        echo   OK  Docker is running
    )

    docker compose version >nul 2>&1
    if not errorlevel 1 (
        echo   OK  docker compose ^(v2^)
    ) else (
        docker-compose --version >nul 2>&1
        if not errorlevel 1 (
            echo   OK  docker-compose ^(v1^)
        ) else (
            echo   !   docker-compose not found — update Docker Desktop
        )
    )
)

REM =============================================================================
REM  Done
REM =============================================================================
echo.
echo  ==========================================
echo   Setup complete!
echo.
echo     Manual TUI    (no Docker needed)
echo       start.bat
echo.
echo     Live Monitor  (requires Docker)
echo       start.bat --live
echo.
echo     REST API
echo       start.bat --api
echo.
pause
