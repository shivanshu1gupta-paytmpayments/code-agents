#!/usr/bin/env bash
# ============================================================================
# Code Agents — One-Command Installer
# ============================================================================
# Installs code-agents centrally at ~/.code-agents
# Then use 'code-agents init' in any repo to configure and run.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/shivanshu1gupta-paytmpayments/code-agents/main/install.sh | bash
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

CODE_AGENTS_DIR="$HOME/.code-agents"
REPO_URL="https://github.com/shivanshu1gupta-paytmpayments/code-agents.git"

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${CYAN}  ╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}  ║     Code Agents — One-Command Installer      ║${RESET}"
echo -e "${BOLD}${CYAN}  ╚══════════════════════════════════════════════╝${RESET}"
echo ""

# ============================================================================
# STEP 1: Check Python
# ============================================================================
step "1/5" "Checking Python..."

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
    echo "  Install: https://www.python.org/downloads/"
    echo "  macOS:   brew install python@3.12"
    echo "  Ubuntu:  sudo apt install python3.12"
    exit 1
fi

info "$("$PYTHON_CMD" --version 2>&1)"

# ============================================================================
# STEP 2: Check/Install Poetry
# ============================================================================
step "2/5" "Checking Poetry..."

if command -v poetry &>/dev/null; then
    info "$(poetry --version 2>&1)"
else
    warn "Poetry not found. Installing..."
    curl -sSL https://install.python-poetry.org | "$PYTHON_CMD" - 2>&1 | tail -3
    export PATH="$HOME/.local/bin:$PATH"
    if command -v poetry &>/dev/null; then
        info "Poetry installed: $(poetry --version)"
    else
        error "Poetry installation failed. Install manually: https://python-poetry.org/docs/"
        exit 1
    fi
fi

# ============================================================================
# STEP 3: Clone / Update code-agents
# ============================================================================
step "3/5" "Installing Code Agents to ~/.code-agents..."

if [ -f "$CODE_AGENTS_DIR/pyproject.toml" ]; then
    info "Already installed at: $CODE_AGENTS_DIR"
    cd "$CODE_AGENTS_DIR"

    # Check current version before pull
    OLD_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

    dim "Pulling latest from GitHub..."
    PULL_OUTPUT=$(git pull 2>&1)
    PULL_STATUS=$?

    if [ $PULL_STATUS -ne 0 ]; then
        warn "Could not pull latest (offline or merge conflict?)"
        dim "    $PULL_OUTPUT"
    elif echo "$PULL_OUTPUT" | grep -q "Already up to date"; then
        info "Already up to date (${OLD_COMMIT})"
    else
        NEW_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        info "Updated: ${OLD_COMMIT} → ${NEW_COMMIT}"
        echo ""
        dim "  Files updated:"

        # Show which files changed
        CHANGED=$(git diff --name-only "${OLD_COMMIT}..${NEW_COMMIT}" 2>/dev/null)
        if [ -n "$CHANGED" ]; then
            CHANGED_COUNT=$(echo "$CHANGED" | wc -l | tr -d ' ')
            echo "$CHANGED" | while read -r file; do
                dim "    • $file"
            done
            echo ""
            info "${CHANGED_COUNT} file(s) updated"
        fi

        # Show commit messages
        COMMITS=$(git log --oneline "${OLD_COMMIT}..${NEW_COMMIT}" 2>/dev/null)
        if [ -n "$COMMITS" ]; then
            echo ""
            dim "  Changes:"
            echo "$COMMITS" | while read -r line; do
                dim "    $line"
            done
        fi
    fi
else
    dim "Cloning from GitHub..."
    git clone "$REPO_URL" "$CODE_AGENTS_DIR" 2>&1 | tail -2
    info "Installed to: $CODE_AGENTS_DIR"

    # Show what was cloned
    cd "$CODE_AGENTS_DIR"
    FILE_COUNT=$(git ls-files | wc -l | tr -d ' ')
    COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    info "Cloned ${FILE_COUNT} files (commit: ${COMMIT})"
fi

# ============================================================================
# STEP 4: Install dependencies
# ============================================================================
step "4/5" "Installing dependencies..."

cd "$CODE_AGENTS_DIR"
dim "poetry install (includes claude-agent-sdk)..."
poetry install --quiet 2>&1 | tail -5
info "Core dependencies installed (includes claude-agent-sdk)"

# cursor-agent-sdk (optional — for Cursor backend)
if ! poetry run python -c "import cursor_agent_sdk" 2>/dev/null; then
    dim "Installing cursor-agent-sdk (Cursor backend)..."
    poetry install --with cursor --quiet 2>&1 | tail -3
fi
info "cursor-agent-sdk ready"

# Add to PATH
POETRY_BIN="$(cd "$CODE_AGENTS_DIR" && poetry env info -p 2>/dev/null)/bin"
SHELL_RC=""
if [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
fi

# Create a wrapper script in ~/.local/bin
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/code-agents" << 'WRAPPER'
#!/usr/bin/env bash
# Code Agents CLI wrapper — runs 'code-agents' from ~/.code-agents
# Captures the user's working directory so agents work on THEIR repo
export CODE_AGENTS_USER_CWD="$(pwd)"
cd "$HOME/.code-agents" && poetry run code-agents "$@"
WRAPPER
chmod +x "$HOME/.local/bin/code-agents"

# Ensure ~/.local/bin is in PATH
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    if [ -n "$SHELL_RC" ]; then
        echo '' >> "$SHELL_RC"
        echo '# Code Agents CLI' >> "$SHELL_RC"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        info "Added ~/.local/bin to PATH in $(basename "$SHELL_RC")"
    fi
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install shell tab-completion
dim "Installing shell tab-completion..."
if [ -f "$HOME/.zshrc" ]; then
    if ! grep -q "# code-agents completion" "$HOME/.zshrc" 2>/dev/null; then
        "$HOME/.local/bin/code-agents" completions --zsh >> "$HOME/.zshrc" 2>/dev/null
        info "Tab-completion installed in ~/.zshrc"
    else
        info "Tab-completion already installed in ~/.zshrc"
    fi
elif [ -f "$HOME/.bashrc" ]; then
    if ! grep -q "# code-agents completion" "$HOME/.bashrc" 2>/dev/null; then
        "$HOME/.local/bin/code-agents" completions --bash >> "$HOME/.bashrc" 2>/dev/null
        info "Tab-completion installed in ~/.bashrc"
    else
        info "Tab-completion already installed in ~/.bashrc"
    fi
fi

# ============================================================================
# STEP 5: Done!
# ============================================================================
step "5/5" "Installation complete!"
echo ""
divider
echo ""
echo -e "  ${BOLD}${GREEN}Code Agents is installed!${RESET}"
echo ""
echo -e "  ${BOLD}How to use:${RESET}"
echo ""
echo -e "    ${CYAN}# Go to any git repo and initialize:${RESET}"
echo -e "    ${BOLD}cd /path/to/your-project${RESET}"
echo -e "    ${BOLD}code-agents init${RESET}"
echo ""
echo -e "    ${DIM}This will:${RESET}"
echo -e "    ${DIM}  1. Ask for API keys (Cursor/Claude) → saved to ~/.code-agents/config.env${RESET}"
echo -e "    ${DIM}  2. Ask for Jenkins/ArgoCD config (optional) → saved to .env.code-agents${RESET}"
echo -e "    ${DIM}  3. Start the server pointing at your repo${RESET}"
echo ""
echo -e "    ${CYAN}# After init, just start the server:${RESET}"
echo -e "    ${BOLD}cd /path/to/your-project${RESET}"
echo -e "    ${BOLD}code-agents start${RESET}"
echo ""
echo -e "    ${CYAN}# Other commands:${RESET}"
echo -e "    ${BOLD}code-agents help${RESET}     ${DIM}— show all commands${RESET}"
echo -e "    ${BOLD}code-agents init${RESET}     ${DIM}— configure in current repo${RESET}"
echo -e "    ${BOLD}code-agents start${RESET}    ${DIM}— start server${RESET}"
echo -e "    ${BOLD}code-agents setup${RESET}    ${DIM}— full setup wizard${RESET}"
echo ""
divider
echo ""
echo -e "  ${DIM}Restart your terminal (or run: source ${SHELL_RC:-~/.zshrc}) then:${RESET}"
echo ""
echo -e "    ${BOLD}cd your-project && code-agents init${RESET}"
echo ""
