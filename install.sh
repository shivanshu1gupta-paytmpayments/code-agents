#!/usr/bin/env bash
# ============================================================================
# Code Agents — One-Command Installer
# ============================================================================
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/shivanshu1gupta-paytmpayments/code-agents/main/install.sh | bash
#   or:
#   ./install.sh
#   or (from your target repo):
#   bash /path/to/code-agents/install.sh
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
if [ -t 1 ]; then
    BOLD='\033[1m'
    GREEN='\033[32m'
    YELLOW='\033[33m'
    RED='\033[31m'
    CYAN='\033[36m'
    DIM='\033[2m'
    RESET='\033[0m'
else
    BOLD='' GREEN='' YELLOW='' RED='' CYAN='' DIM='' RESET=''
fi

info()    { echo -e "${GREEN}  ✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}  !${RESET} $*"; }
error()   { echo -e "${RED}  ✗${RESET} $*"; }
step()    { echo -e "\n${BOLD}${CYAN}[$1]${RESET} ${BOLD}$2${RESET}"; }
dim()     { echo -e "${DIM}    $*${RESET}"; }
ask()     { echo -en "  $1 "; }
divider() { echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"; }

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${CYAN}  ╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}  ║     Code Agents — One-Command Installer      ║${RESET}"
echo -e "${BOLD}${CYAN}  ╚══════════════════════════════════════════════╝${RESET}"
echo ""

# ---------------------------------------------------------------------------
# Detect where code-agents lives
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
if [ -f "$SCRIPT_DIR/pyproject.toml" ] && grep -q 'code-agents' "$SCRIPT_DIR/pyproject.toml" 2>/dev/null; then
    CODE_AGENTS_DIR="$SCRIPT_DIR"
else
    # If run via curl pipe, we need to clone
    CODE_AGENTS_DIR="$HOME/.code-agents"
fi

TARGET_REPO="$(pwd)"

# ============================================================================
# STEP 1: Check Python
# ============================================================================
step "1/8" "Checking Python..."

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    error "Python 3.10+ is required but not found."
    echo "  Install Python from: https://www.python.org/downloads/"
    echo "  macOS: brew install python@3.12"
    echo "  Ubuntu: sudo apt install python3.12"
    exit 1
fi

PYTHON_VERSION=$("$PYTHON_CMD" --version 2>&1)
info "$PYTHON_VERSION"

# ============================================================================
# STEP 2: Check/Install Poetry
# ============================================================================
step "2/8" "Checking Poetry..."

if command -v poetry &>/dev/null; then
    POETRY_VERSION=$(poetry --version 2>&1)
    info "$POETRY_VERSION"
else
    warn "Poetry not found. Installing..."
    dim "curl -sSL https://install.python-poetry.org | $PYTHON_CMD -"
    curl -sSL https://install.python-poetry.org | "$PYTHON_CMD" - 2>&1 | tail -3
    export PATH="$HOME/.local/bin:$PATH"
    if command -v poetry &>/dev/null; then
        info "Poetry installed: $(poetry --version)"
    else
        error "Poetry installation failed."
        echo "  Install manually: https://python-poetry.org/docs/#installation"
        exit 1
    fi
fi

# ============================================================================
# STEP 3: Get code-agents project
# ============================================================================
step "3/8" "Setting up Code Agents project..."

if [ -f "$CODE_AGENTS_DIR/pyproject.toml" ]; then
    info "Found at: $CODE_AGENTS_DIR"
else
    warn "Cloning code-agents..."
    dim "git clone → $CODE_AGENTS_DIR"
    # Replace with your actual repo URL
    git clone https://github.com/shivanshu1gupta-paytmpayments/code-agents.git "$CODE_AGENTS_DIR" 2>&1 | tail -2
    info "Cloned to: $CODE_AGENTS_DIR"
fi

# ============================================================================
# STEP 4: Install dependencies
# ============================================================================
step "4/8" "Installing dependencies..."

cd "$CODE_AGENTS_DIR"
dim "poetry install (this may take a minute)..."
poetry install --quiet 2>&1 | tail -5
info "Dependencies installed"

# Check for cursor-agent SDK
if poetry run python -c "import cursor_agent_sdk" 2>/dev/null; then
    info "cursor-agent-sdk available"
else
    warn "cursor-agent-sdk not installed (optional — needed for Cursor backend)"
    ask "Install cursor-agent-sdk? [Y/n]:"
    read -r yn
    if [ "${yn:-y}" != "n" ] && [ "${yn:-y}" != "N" ]; then
        dim "poetry install --with cursor..."
        poetry install --with cursor --quiet 2>&1 | tail -3
        info "cursor-agent-sdk installed"
    fi
fi

# ============================================================================
# STEP 5: Detect target repo
# ============================================================================
step "5/8" "Target Repository..."

if [ -d "$TARGET_REPO/.git" ]; then
    info "Detected git repo: $TARGET_REPO"
else
    warn "No git repo at current directory: $TARGET_REPO"
    ask "Enter path to your target repo (or press Enter for current dir):"
    read -r custom_path
    TARGET_REPO="${custom_path:-$TARGET_REPO}"
fi

# ============================================================================
# STEP 6: Interactive setup (keys & config)
# ============================================================================
step "6/8" "Configuration..."
echo ""

cd "$CODE_AGENTS_DIR"
poetry run code-agents-setup <<< "" 2>/dev/null && true

# If setup module didn't run (e.g., non-interactive), fall back to manual .env
if [ ! -f "$CODE_AGENTS_DIR/.env" ]; then
    echo ""
    divider
    echo -e "  ${BOLD}Manual .env setup needed${RESET}"
    divider
    echo ""

    ENV_FILE="$CODE_AGENTS_DIR/.env"

    # Backend key
    echo -e "  ${BOLD}Backend API Key${RESET} (required)"
    ask "CURSOR_API_KEY (paste your key):"
    read -rs cursor_key
    echo ""

    # Server config
    ask "HOST [0.0.0.0]:"
    read -r host
    host="${host:-0.0.0.0}"

    ask "PORT [8000]:"
    read -r port
    port="${port:-8000}"

    # Jenkins (optional)
    ask "Configure Jenkins CI/CD? [y/N]:"
    read -r jenkins_yn
    jenkins_url="" jenkins_user="" jenkins_token="" jenkins_build="" jenkins_deploy=""
    if [ "${jenkins_yn}" = "y" ] || [ "${jenkins_yn}" = "Y" ]; then
        ask "  JENKINS_URL:"
        read -r jenkins_url
        ask "  JENKINS_USERNAME:"
        read -r jenkins_user
        ask "  JENKINS_API_TOKEN:"
        read -rs jenkins_token
        echo ""
        ask "  JENKINS_BUILD_JOB (path, not URL):"
        read -r jenkins_build
        ask "  JENKINS_DEPLOY_JOB (path, not URL):"
        read -r jenkins_deploy
    fi

    # ArgoCD (optional)
    ask "Configure ArgoCD? [y/N]:"
    read -r argocd_yn
    argocd_url="" argocd_token="" argocd_app=""
    if [ "${argocd_yn}" = "y" ] || [ "${argocd_yn}" = "Y" ]; then
        ask "  ARGOCD_URL:"
        read -r argocd_url
        ask "  ARGOCD_AUTH_TOKEN:"
        read -rs argocd_token
        echo ""
        ask "  ARGOCD_APP_NAME:"
        read -r argocd_app
    fi

    # Write .env
    cat > "$ENV_FILE" << ENVEOF
# Generated by code-agents installer

# Core
CURSOR_API_KEY=${cursor_key}

# Server
HOST=${host}
PORT=${port}

# Target Repository
TARGET_REPO_PATH=${TARGET_REPO}

# Jenkins
JENKINS_URL=${jenkins_url}
JENKINS_USERNAME=${jenkins_user}
JENKINS_API_TOKEN=${jenkins_token}
JENKINS_BUILD_JOB=${jenkins_build}
JENKINS_DEPLOY_JOB=${jenkins_deploy}

# ArgoCD
ARGOCD_URL=${argocd_url}
ARGOCD_AUTH_TOKEN=${argocd_token}
ARGOCD_APP_NAME=${argocd_app}
ENVEOF

    chmod 600 "$ENV_FILE"
    info ".env written to $ENV_FILE"
fi

# ============================================================================
# STEP 7: Verify installation
# ============================================================================
step "7/8" "Verifying installation..."

cd "$CODE_AGENTS_DIR"

# Check agents load
AGENT_COUNT=$(poetry run python -c "
from code_agents.config import agent_loader
agent_loader.load()
print(len(agent_loader.list_agents()))
" 2>/dev/null || echo "0")

if [ "$AGENT_COUNT" -gt 0 ]; then
    info "$AGENT_COUNT agents loaded"
else
    error "No agents loaded — check agents/ directory"
fi

# Check .env has required keys
if [ -f "$CODE_AGENTS_DIR/.env" ]; then
    info ".env file exists"
else
    warn ".env not found — server may not work without API keys"
fi

# Show log location
mkdir -p "$CODE_AGENTS_DIR/logs"
info "Logs: $CODE_AGENTS_DIR/logs/code-agents.log"

# ============================================================================
# STEP 8: Launch
# ============================================================================
step "8/8" "Ready to launch!"
echo ""
divider
echo ""
echo -e "  ${BOLD}Installation complete!${RESET}"
echo ""
echo -e "  Project:    ${CYAN}$CODE_AGENTS_DIR${RESET}"
echo -e "  Target repo: ${CYAN}$TARGET_REPO${RESET}"
echo -e "  Logs:        ${CYAN}$CODE_AGENTS_DIR/logs/code-agents.log${RESET}"
echo ""
echo -e "  ${BOLD}Quick commands:${RESET}"
echo -e "    ${DIM}# Start the server${RESET}"
echo -e "    cd $CODE_AGENTS_DIR && poetry run code-agents"
echo ""
echo -e "    ${DIM}# Re-run setup wizard${RESET}"
echo -e "    cd $CODE_AGENTS_DIR && poetry run code-agents-setup"
echo ""
echo -e "    ${DIM}# Check server health${RESET}"
echo -e "    curl http://localhost:8000/health"
echo ""
echo -e "    ${DIM}# View live logs${RESET}"
echo -e "    tail -f $CODE_AGENTS_DIR/logs/code-agents.log"
echo ""
divider
echo ""

ask "Start the server now? [Y/n]:"
read -r start_yn
if [ "${start_yn:-y}" != "n" ] && [ "${start_yn:-y}" != "N" ]; then
    echo ""
    echo -e "  ${BOLD}${CYAN}Starting Code Agents...${RESET}"
    echo -e "  ${DIM}Press Ctrl+C to stop${RESET}"
    echo ""
    cd "$CODE_AGENTS_DIR"
    poetry run code-agents
else
    echo ""
    info "Run later with: cd $CODE_AGENTS_DIR && poetry run code-agents"
    echo ""
fi
