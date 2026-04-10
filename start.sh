#!/usr/bin/env bash
# =============================================================================
# start.sh — Insurance PAS Live Monitor · Launcher
# Supports: macOS · Linux · Windows (Git Bash / WSL)
#
# Usage:
#   ./start.sh              → Manual query TUI  (no Docker needed)
#   ./start.sh --live       → Split-screen live monitor (Docker + MySQL)
#   ./start.sh --api        → REST API server (uvicorn)
#   ./start.sh --live --no-tui → Console-only live demo
# =============================================================================
set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
if [ -t 1 ] && command -v tput &>/dev/null; then
    ORANGE=$(tput setaf 3)
    GREEN=$(tput setaf 2)
    RED=$(tput setaf 1)
    DIM=$(tput dim)
    BOLD=$(tput bold)
    RESET=$(tput sgr0)
else
    ORANGE="" GREEN="" RED="" DIM="" BOLD="" RESET=""
fi

OK="${GREEN}✓${RESET}"
INFO="${ORANGE}›${RESET}"

ok()   { echo "  ${OK}  $1"; }
warn() { echo "  ${ORANGE}⚠${RESET}  $1"; }
fail() { echo "  ${RED}✗${RESET}  $1"; exit 1; }

# ── Detect OS ─────────────────────────────────────────────────────────────────
case "$(uname -s 2>/dev/null)" in
    Darwin)  OS="mac"   ;;
    Linux)   OS="linux" ;;
    MINGW*|MSYS*|CYGWIN*) OS="win_bash" ;;
    *)       OS="unknown" ;;
esac

# ── Parse args ────────────────────────────────────────────────────────────────
MODE="manual"   # manual | live | api
NO_TUI=false

for arg in "$@"; do
    case "$arg" in
        --live)    MODE="live" ;;
        --api)     MODE="api"  ;;
        --no-tui)  NO_TUI=true ;;
        --help|-h)
            echo ""
            echo "${BOLD}${ORANGE}Insurance PAS · Live Monitor${RESET}"
            echo ""
            echo "  ${BOLD}./start.sh${RESET}              Manual query TUI (no Docker)"
            echo "  ${BOLD}./start.sh --live${RESET}       Split-screen live monitor"
            echo "  ${BOLD}./start.sh --live --no-tui${RESET}  Console-only live demo"
            echo "  ${BOLD}./start.sh --api${RESET}        REST API on http://localhost:8000"
            echo ""
            exit 0
            ;;
    esac
done

# ── Activate venv ─────────────────────────────────────────────────────────────
if [ "$OS" = "win_bash" ]; then
    ACTIVATE="venv/Scripts/activate"
else
    ACTIVATE="venv/bin/activate"
fi

if [ ! -f "$ACTIVATE" ]; then
    fail "venv not found — run ./setup.sh first"
fi

# shellcheck disable=SC1090
source "$ACTIVATE"

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "${BOLD}${ORANGE}Insurance PAS · Live Monitor${RESET}"
echo "${DIM}─────────────────────────────────────────${RESET}"

# =============================================================================
# MODE: manual — single-query TUI (no Docker)
# =============================================================================
if [ "$MODE" = "manual" ]; then
    echo "  ${INFO}  Mode: ${BOLD}Manual Query TUI${RESET}"
    echo "  ${DIM}Ask about SQL performance, explore cases, detect anomalies${RESET}"
    echo ""
    python cli/tui.py
    exit 0
fi

# =============================================================================
# MODE: api — REST API
# =============================================================================
if [ "$MODE" = "api" ]; then
    echo "  ${INFO}  Mode: ${BOLD}REST API${RESET}"
    echo "  ${DIM}Endpoints: /health  /analyze/query  /detect/anomaly  /feedback${RESET}"
    echo "  ${DIM}Docs:      http://localhost:8000/docs${RESET}"
    echo ""
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
    exit 0
fi

# =============================================================================
# MODE: live — split-screen live monitor (requires Docker + MySQL)
# =============================================================================
echo "  ${INFO}  Mode: ${BOLD}Live Monitor${RESET} (PAS + AI split-screen)"
echo ""

# ── Docker check ─────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    fail "Docker not found. Install Docker Desktop: https://docker.com/products/docker-desktop"
fi

if ! docker info &>/dev/null 2>&1; then
    fail "Docker is not running. Start Docker Desktop, then retry."
fi

# ── Fix initdb permissions (Docker requires world-readable) ───────────────────
chmod -R a+rX docker/initdb/ 2>/dev/null || true

# ── Start MySQL container ─────────────────────────────────────────────────────
echo "  ${INFO}  Starting MySQL (Docker)..."

if docker compose version &>/dev/null 2>&1; then
    COMPOSE="docker compose"
else
    COMPOSE="docker-compose"
fi

$COMPOSE up -d

ok "MySQL container started (port 3307)"

# ── Wait for MySQL to be ready ────────────────────────────────────────────────
echo "  ${INFO}  Waiting for MySQL to be ready..."
echo "  ${DIM}  (First run downloads + imports 4.1M rows — can take 5-10 min)${RESET}"

python - <<'PYEOF'
import sys
import time

try:
    import mysql.connector
except ImportError:
    print("  ✗  mysql-connector-python not installed — run ./setup.sh")
    sys.exit(1)

MAX_WAIT = 600   # 10 minutes (first run downloads ~30MB then imports 4.1M rows)
INTERVAL = 5
elapsed = 0
last_error = ""

while elapsed < MAX_WAIT:
    try:
        cnx = mysql.connector.connect(
            host="localhost", port=3307,
            user="monitor", password="monitor_pw",
            database="employees", connection_timeout=5,
            use_pure=True,  # avoid C-extension handshake issues on some Linux setups
        )
        # Verify employees table exists and is fully imported
        cur = cnx.cursor()
        cur.execute("SELECT COUNT(*) FROM employees")
        count = cur.fetchone()[0]
        cur.close()
        cnx.close()
        if count > 0:
            print(f"\n  ✓  MySQL ready — employees table has {count:,} rows")
            sys.exit(0)
        else:
            last_error = "employees table empty (import still running?)"
    except Exception as exc:
        last_error = str(exc)
    mins = elapsed // 60
    secs = elapsed % 60
    # Show a helpful hint the first time we see the init error
    if elapsed == INTERVAL and "initial communication" in last_error:
        sys.stdout.write("\n  (This is NORMAL during first run — MySQL is importing data, keep waiting)\n")
    sys.stdout.write(f"\r  ›  Waiting... {mins}m{secs:02d}s  [{last_error[:55]}]")  
    sys.stdout.flush()
    time.sleep(INTERVAL)
    elapsed += INTERVAL

print(f"\n  ✗  MySQL not ready after {MAX_WAIT//60} minutes")
print(f"     Last error: {last_error}")
print("     Check container logs: docker compose logs mysql")
sys.exit(1)
PYEOF

echo ""

# ── Launch ────────────────────────────────────────────────────────────────────
if [ "$NO_TUI" = true ]; then
    echo "  ${INFO}  Launching console demo..."
    echo ""
    python demo_live.py --no-tui
else
    echo "  ${INFO}  Launching split-screen TUI..."
    echo "  ${DIM}  SPACE = Pause/Resume   Q = Quit${RESET}"
    echo ""
    python demo_live.py
fi
