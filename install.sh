#!/usr/bin/env bash
set -euo pipefail

# CopyClip installer for macOS and Linux
# Usage: curl -fsSL https://raw.githubusercontent.com/sssamuelll/copyclip/main/install.sh | bash

REPO="https://github.com/sssamuelll/copyclip.git"
MIN_PYTHON="3.10"
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
DIM='\033[2m'
NC='\033[0m'

info()  { echo -e "${CYAN}[copyclip]${NC} $1"; }
ok()    { echo -e "${GREEN}[copyclip]${NC} $1"; }
err()   { echo -e "${RED}[copyclip]${NC} $1"; }

# --- Check Python version ---
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo "0")
        minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "0")
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    err "Python ${MIN_PYTHON}+ is required but not found."
    err "Install Python from https://python.org/downloads/ and try again."
    exit 1
fi

info "Found $PYTHON ($($PYTHON --version 2>&1))"

# --- Install via pipx (preferred) or pip ---
if command -v pipx &>/dev/null; then
    info "Installing with pipx (isolated environment)..."
    pipx install "copyclip @ git+${REPO}" --force
elif command -v pip3 &>/dev/null; then
    info "pipx not found, installing with pip3 --user..."
    pip3 install --user "copyclip @ git+${REPO}"
elif "$PYTHON" -m pip --version &>/dev/null; then
    info "pipx not found, installing with $PYTHON -m pip --user..."
    "$PYTHON" -m pip install --user "copyclip @ git+${REPO}"
else
    err "Neither pipx nor pip found. Install pip first:"
    err "  $PYTHON -m ensurepip --upgrade"
    exit 1
fi

# --- Verify installation ---
if command -v copyclip &>/dev/null; then
    ok "copyclip installed successfully!"
    echo -e "${DIM}  $(copyclip --version 2>/dev/null || echo 'copyclip ready')${NC}"
    echo ""
    ok "Get started:"
    echo "  cd your-project"
    echo "  copyclip start"
else
    # copyclip installed but not in PATH
    echo ""
    err "copyclip was installed but is not in your PATH."
    echo ""

    # Try to find where pip installed the script
    SCRIPT_DIR=""
    if command -v pipx &>/dev/null; then
        SCRIPT_DIR="$HOME/.local/bin"
    else
        SCRIPT_DIR=$("$PYTHON" -c "import sysconfig; print(sysconfig.get_path('scripts', 'posix_user'))" 2>/dev/null || echo "$HOME/.local/bin")
    fi

    info "Add this to your shell profile (~/.bashrc, ~/.zshrc, or ~/.profile):"
    echo ""
    echo "  export PATH=\"${SCRIPT_DIR}:\$PATH\""
    echo ""
    info "Then restart your terminal or run:"
    echo "  source ~/.zshrc  # or ~/.bashrc"
fi
