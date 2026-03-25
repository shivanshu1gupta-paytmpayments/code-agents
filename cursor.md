# Cursor Rules — Project Context for Cursor AI

## What This Project Is

Code Agents is an AI-powered code agent platform with interactive chat and a CI/CD pipeline. 13 agents exposed as OpenAI-compatible endpoints. CLI-first: `code-agents init` per repo, `code-agents chat` for interactive use.

## Quick Reference

```bash
# Install
curl -fsSL https://raw.githubusercontent.com/shivanshu1gupta-paytmpayments/code-agents/main/install.sh | bash

# Per-repo setup
cd /path/to/your-project
code-agents init                    # configure keys, write config
code-agents start                   # start server (background)
code-agents chat                    # interactive chat — pick agent from menu

# All CLI commands
code-agents help                    # full help with all args
code-agents start [--fg]            # start server (--fg for foreground)
code-agents shutdown                # stop server
code-agents chat [agent-name]       # interactive chat REPL
code-agents status                  # health + config
code-agents doctor                  # diagnose issues
code-agents restart                 # restart server (shutdown + start)
code-agents rules                   # manage agent rules (list/create/edit/delete)
code-agents completions --install   # install shell tab-completion
code-agents migrate                 # migrate legacy .env to centralized config
code-agents agents                  # list 13 agents
code-agents config                  # show config (secrets masked)
code-agents logs [N]                # tail log file
code-agents branches                # list git branches
code-agents diff [base] [head]      # git diff (default: main HEAD)
code-agents test [branch]           # run tests
code-agents review [base] [head]    # AI code review
code-agents pipeline start [branch] # start CI/CD pipeline
code-agents pipeline status [id]    # pipeline status
code-agents pipeline advance <id>   # advance pipeline step
code-agents pipeline rollback <id>  # rollback deployment
code-agents curls [cat|agent]       # show API curl commands
code-agents setup                   # full setup wizard
code-agents update                  # pull latest code + reinstall deps
code-agents sessions                # list saved chat sessions
code-agents sessions --all          # sessions from all repos
code-agents chat --resume <id>      # resume a saved session
code-agents version                 # version info

# Dev
poetry run pytest                   # 230 tests
```

## Architecture

- **`cli.py`** — 23 CLI commands (init, migrate, rules, start, restart, chat, sessions, shutdown, status, doctor, config, logs, branches, diff, test, review, pipeline, agents, curls, setup, update, version, completions, help)
- **`chat.py`** — Interactive REPL: agent picker menu, streaming, multi-turn sessions with auto-save, `/agent` switching, inline delegation, `/exec`, `/history` + `/resume` for session persistence, tab-completion, auto-detects git repo, auto-starts server
- **`setup.py`** — Interactive setup wizard
- **`env_loader.py`** — Centralized env loading: global (`~/.code-agents/config.env`) + per-repo (`.env.code-agents`)
- **`rules_loader.py`** — Agent rules: global (`~/.code-agents/rules/`) + project (`.code-agents/rules/`), auto-refresh
- **`app.py`** — FastAPI app, CORS, lifespan, request/response logging
- **`backend.py`** — Backend abstraction: cursor CLI, cursor HTTP, claude (claude-agent-sdk built-in)
- **`chat_history.py`** — Chat session persistence: auto-save to `~/.code-agents/chat_history/`, UUID-based IDs, resume
- **`stream.py`** — SSE streaming with ToolUse/ToolResult logging, `build_prompt()` for multi-turn
- **`logging_config.py`** — Hourly rotating log files (7-day retention)
- **CI/CD clients**: `git_client.py`, `testing_client.py`, `jenkins_client.py`, `argocd_client.py`
- **CI/CD routers**: `routers/git_ops.py`, `testing.py`, `jenkins.py`, `argocd.py`, `pipeline.py`
- **`pipeline_state.py`** — 6-step state machine (connect → review/test → build → deploy → verify → rollback)
- **`agents/*.yaml`** — 13 agent definitions
- **`tests/`** — 230 tests

## Key Patterns

- **CLI entry**: `pyproject.toml` → `code-agents = "code_agents.cli:main"`
- **Centralized config**: `code-agents init` writes global config to `~/.code-agents/config.env` (API keys, server) and per-repo config to `.env.code-agents` (Jenkins, ArgoCD). Legacy `.env` still loaded for backward compat.
- **Interactive chat**: `code-agents chat` → numbered menu → REPL with streaming. `/agent` switches permanently. `/<agent> <prompt>` delegates one-shot to another agent. Tab-completion for commands and agent names. Each agent stays in role. Auto-detects git repo from cwd. Auto-starts server if not running.
- **Dynamic `repo_path`**: request param → `TARGET_REPO_PATH` env → `os.getcwd()` (never stored in config)
- **Background server**: `start` launches background process, `shutdown` kills it
- **Chat history**: Sessions auto-saved as JSON to `~/.code-agents/chat_history/`. Full conversation sent with every request. Resume with `--resume <id>` or `/resume`. Manage with `code-agents sessions`.
- **Hourly log rotation**: `logs/code-agents.log` = last hour, 168 backups (7 days)
- **Agent names**: kebab-case in URLs, snake_case in filenames
- **Backends**: `"cursor"` (default), `"claude"` (API), or `"claude-cli"` (subscription, no API key). Set `CODE_AGENTS_BACKEND=claude-cli` globally to override all agents.

## Environment Variables

Global (`~/.code-agents/config.env`):
- `CODE_AGENTS_BACKEND` — `claude-cli` to use Claude subscription instead of API keys
- `CODE_AGENTS_CLAUDE_CLI_MODEL` — model for claude-cli (default: `claude-sonnet-4-6`)
- `CURSOR_API_KEY` / `ANTHROPIC_API_KEY` — Backend keys
- `HOST` / `PORT` — Server bind (default `0.0.0.0:8000`)
- `REDASH_*`, `ELASTICSEARCH_*`, `ATLASSIAN_*` — Integrations

Per-repo (`.env.code-agents`):
- `JENKINS_URL`, `JENKINS_USERNAME`, `JENKINS_API_TOKEN`, `JENKINS_BUILD_JOB`, `JENKINS_DEPLOY_JOB`
- `ARGOCD_URL`, `ARGOCD_AUTH_TOKEN`, `ARGOCD_APP_NAME`
- `TARGET_TEST_COMMAND`, `TARGET_COVERAGE_THRESHOLD`

Runtime (never stored): `TARGET_REPO_PATH` — auto-detected from cwd

## Testing

230 tests — `poetry run pytest`. Covers: chat REPL (slash commands, agent parsing, SSE streaming, repo detection, inline delegation, tab-completion, command extraction, placeholders, welcome messages), centralized env loading (split_vars, load order, var classification), rules loader (merge order, agent targeting, auto-refresh), CLI (all 23 commands, help completeness, config, curls, dispatcher), git operations, test framework detection, coverage XML, Jenkins/ArgoCD client init + job path + build version extraction, all routers, pipeline lifecycle, health/diagnostics.

## Adding a New Agent

1. Create `agents/<name>.yaml`
2. Add to `agents/agent_router.yaml` system prompt
3. Add to `Agents.md`, `README.md`
4. Add role to `AGENT_ROLES` in `chat.py`
