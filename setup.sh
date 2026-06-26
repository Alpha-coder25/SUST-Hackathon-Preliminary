#!/usr/bin/env bash
# =============================================================================
# QueueStorm Investigator — Auto Setup & Run Script
# =============================================================================
# This script:
#   1. Checks for Python 3.11+
#   2. Creates a virtual environment (if missing)
#   3. Installs all dependencies from requirements.txt
#   4. Starts the QueueStorm API server
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh              # Install deps & start server
#   ./setup.sh --test       # Install deps, start server & run tests
#   ./setup.sh --help       # Show this help message
# =============================================================================

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
REQUIREMENTS="$PROJECT_DIR/requirements.txt"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── Helper Functions ──────────────────────────────────────────────────────────

info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

cleanup() {
    if [ -n "${SERVER_PID:-}" ]; then
        info "Stopping server (PID: $SERVER_PID)..."
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        ok "Server stopped."
    fi
}
trap cleanup EXIT INT TERM

# ── Help ──────────────────────────────────────────────────────────────────────

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    echo ""
    echo "QueueStorm Investigator — Setup & Run Script"
    echo ""
    echo "Usage:"
    echo "  ./setup.sh              Install dependencies & start the server"
    echo "  ./setup.sh --test       Install deps, start server & run test suite"
    echo "  ./setup.sh --help       Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  HOST=0.0.0.0            Server bind address"
    echo "  PORT=8000               Server port"
    echo "  LOG_LEVEL=INFO          Logging level (DEBUG, INFO, WARNING, ERROR)"
    echo ""
    exit 0
fi

# ── Step 1: Check Python ──────────────────────────────────────────────────────

echo ""
echo "=============================================="
echo "  QueueStorm Investigator — Setup"
echo "=============================================="
echo ""

info "Step 1/4: Checking Python installation..."

# Check if python3 exists, fallback to python
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    error "Python is not installed. Please install Python 3.11 or later."
    error "Visit: https://www.python.org/downloads/"
    exit 1
fi

# Check Python version
PY_VERSION=$("$PYTHON" --version 2>&1 | awk '{print $2}')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

info "Found Python $PY_VERSION"

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    warn "Python 3.11+ is recommended. You have $PY_VERSION."
    warn "Continuing anyway, but some features may not work."
else
    ok "Python $PY_VERSION meets the minimum requirement (3.11+)."
fi

# ── Step 2: Virtual Environment ────────────────────────────────────────────────

info "Step 2/4: Setting up virtual environment..."

# Check if venv module is available
if ! "$PYTHON" -m venv --help &>/dev/null; then
    error "Python venv module is not available."
    error "Install it with: pip install virtualenv"
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment at $VENV_DIR..."
    "$PYTHON" -m venv "$VENV_DIR"
    ok "Virtual environment created."
else
    ok "Virtual environment already exists."
fi

# Activate virtual environment
# Determine the activate script path
if [ -f "$VENV_DIR/bin/activate" ]; then
    # Linux/macOS/WSL
    source "$VENV_DIR/bin/activate"
elif [ -f "$VENV_DIR/Scripts/activate" ]; then
    # Windows (Git Bash / MSYS2)
    source "$VENV_DIR/Scripts/activate"
else
    error "Cannot find virtual environment activation script."
    exit 1
fi

ok "Virtual environment activated."

# ── Step 3: Install Dependencies ───────────────────────────────────────────────

info "Step 3/4: Installing dependencies..."

if [ ! -f "$REQUIREMENTS" ]; then
    error "requirements.txt not found at $REQUIREMENTS"
    exit 1
fi

# Upgrade pip first
info "Upgrading pip..."
"$PYTHON" -m pip install --quiet --upgrade pip
ok "Pip upgraded."

# Install from requirements.txt
info "Installing packages from requirements.txt..."
"$PYTHON" -m pip install --quiet -r "$REQUIREMENTS"
ok "All dependencies installed successfully."

# ── Step 4: Run Server ─────────────────────────────────────────────────────────

info "Step 4/4: Starting the server..."

cd "$PROJECT_DIR"

# Create .env from .env.example if it doesn't exist
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    info "Creating .env from .env.example..."
    cp .env.example .env
    warn ".env created from template. Edit it if you need custom settings."
fi

echo ""
echo "=============================================="
echo "  Starting QueueStorm Investigator API"
echo "  Host: $HOST"
echo "  Port: $PORT"
echo "  Log Level: $LOG_LEVEL"
echo "=============================================="
echo ""

# Start the server in the background
"$PYTHON" -m uvicorn main:app --host "$HOST" --port "$PORT" &
SERVER_PID=$!

# Wait for the server to be ready
info "Waiting for server to start..."
for i in $(seq 1 30); do
    if "$PYTHON" -c "import urllib.request; urllib.request.urlopen('http://$HOST:$PORT/health')" 2>/dev/null; then
        echo ""
        ok "Server is ready! Listening on http://$HOST:$PORT"
        echo ""
        echo "  Try it out:"
        echo "    curl http://$HOST:$PORT/health"
        echo "    curl -X POST http://$HOST:$PORT/analyze-ticket \\"
        echo "      -H 'Content-Type: application/json' \\"
        echo "      -d @sample_cases.json"
        echo ""
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo ""
        error "Server failed to start within 30 seconds. Check the logs above."
        exit 1
    fi
    sleep 1
done

# ── Optional: Run Tests ────────────────────────────────────────────────────────

if [ "${1:-}" = "--test" ]; then
    echo ""
    echo "=============================================="
    echo "  Running Test Suite"
    echo "=============================================="
    echo ""

    if [ -f "$PROJECT_DIR/test_runner.py" ] && [ -f "$PROJECT_DIR/sample_cases.json" ]; then
        "$PYTHON" "$PROJECT_DIR/test_runner.py"
        TEST_EXIT=$?
        echo ""
        if [ $TEST_EXIT -eq 0 ]; then
            ok "All tests passed!"
        else
            error "Some tests failed. Review the output above."
        fi
    else
        warn "Test files not found. Skipping tests."
        warn "Expected: test_runner.py and sample_cases.json"
    fi

    # If --test was the only flag, keep the server running
    # so the user can interact with it
    echo ""
    info "Server is still running (PID: $SERVER_PID). Press Ctrl+C to stop."
    # Wait for Ctrl+C
    wait "$SERVER_PID"
else
    # Keep the server running in foreground
    # (Since we started it in the background, just wait)
    info "Server is running (PID: $SERVER_PID). Press Ctrl+C to stop."
    wait "$SERVER_PID"
fi
