#!/usr/bin/env bash
# =============================================================================
# setup.sh — Insurance PAS Live Monitor · One-time setup
# Supports: macOS · Linux · Windows (Git Bash / WSL)
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
FAIL="${RED}✗${RESET}"
INFO="${ORANGE}›${RESET}"

# ── Helpers ───────────────────────────────────────────────────────────────────
step()  { echo "${BOLD}${ORANGE}[$1]${RESET} $2"; }
ok()    { echo "  ${OK}  $1"; }
warn()  { echo "  ${ORANGE}⚠${RESET}  $1"; }
fail()  { echo "  ${FAIL}  $1"; exit 1; }

# ── Detect OS ─────────────────────────────────────────────────────────────────
case "$(uname -s 2>/dev/null)" in
    Darwin)  OS="mac"   ;;
    Linux)   OS="linux" ;;
    MINGW*|MSYS*|CYGWIN*) OS="win_bash" ;;
    *)       OS="unknown" ;;
esac

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "${BOLD}${ORANGE}Insurance PAS · Live Monitor — Setup${RESET}"
echo "${DIM}─────────────────────────────────────────${RESET}"
echo ""

# =============================================================================
# STEP 1 — Python 3.12+
# =============================================================================
step "1/5" "Checking Python"

PYTHON=""
for cmd in python3 python python3.12 python3.13; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        MAJOR=$("$cmd" -c "import sys; print(sys.version_info.major)")
        MINOR=$("$cmd" -c "import sys; print(sys.version_info.minor)")
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 12 ]; then
            PYTHON="$cmd"
            ok "Python $VER ($cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python 3.12+ is required. Download from https://python.org/downloads/"
fi

# =============================================================================
# STEP 2 — Virtual environment
# =============================================================================
step "2/5" "Virtual environment"

if [ ! -d "venv" ]; then
    echo "  ${INFO}  Creating venv..."
    "$PYTHON" -m venv venv
    ok "venv created"
else
    ok "venv already exists"
fi

# Activate venv (cross-platform)
if [ "$OS" = "win_bash" ]; then
    ACTIVATE="venv/Scripts/activate"
else
    ACTIVATE="venv/bin/activate"
fi

if [ ! -f "$ACTIVATE" ]; then
    fail "venv activation script not found at $ACTIVATE — delete venv/ and rerun"
fi

# shellcheck disable=SC1090
source "$ACTIVATE"
ok "venv activated"

# =============================================================================
# STEP 3 — Dependencies
# =============================================================================
step "3/5" "Installing dependencies"

pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
ok "All packages installed (requirements.txt)"

# =============================================================================
# STEP 4 — Environment file
# =============================================================================
step "4/5" "Environment (.env)"

if [ ! -f ".env" ]; then
    cp .env.example .env
    ok ".env created from .env.example"
    warn "Edit .env to add your LLM API key (optional — works offline too)"
else
    ok ".env already exists"
fi

# =============================================================================
# STEP 5 — Docker check
# =============================================================================
step "5/5" "Docker (for live MySQL demo)"

DOCKER_OK=false
if command -v docker &>/dev/null; then
    if docker info &>/dev/null 2>&1; then
        DOCKER_OK=true
        ok "Docker is running"
    else
        warn "Docker is installed but not running — start Docker Desktop first"
    fi

    # Check compose (v2 plugin or v1 standalone)
    if docker compose version &>/dev/null 2>&1; then
        ok "docker compose (v2 plugin)"
    elif command -v docker-compose &>/dev/null; then
        ok "docker-compose (v1 standalone)"
    else
        warn "docker-compose not found — install Docker Desktop >= 3.6 (includes compose)"
    fi
else
    warn "Docker not found — install Docker Desktop from https://docker.com/products/docker-desktop"
    warn "Docker is only needed for the live MySQL demo (start.sh --live)"
fi

# =============================================================================
# Done
# =============================================================================
echo ""
echo "${DIM}─────────────────────────────────────────${RESET}"
echo "${BOLD}${GREEN}Setup complete!${RESET}"
echo ""
echo "  ${INFO}  ${BOLD}Manual TUI${RESET}  (no Docker needed)"
echo "       ${DIM}./start.sh${RESET}"
echo ""
echo "  ${INFO}  ${BOLD}Live Monitor${RESET}  (requires Docker)"
echo "       ${DIM}./start.sh --live${RESET}"
echo ""
echo "  ${INFO}  ${BOLD}REST API${RESET}"
echo "       ${DIM}./start.sh --api${RESET}"
echo ""
