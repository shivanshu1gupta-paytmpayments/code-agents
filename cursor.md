# Cursor Rules — Project Context for Cursor AI

## What This Project Is

Code Agents is an AI-powered code agent platform with interactive chat and a CI/CD pipeline. 12 agents exposed as OpenAI-compatible endpoints. CLI-first: `code-agents init` per repo, `code-agents chat` for interactive use.

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
code-agents migrate                 # migrate legacy .env to centralized config
code-agents agents                  # list 12 agents
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
code-agents version                 # version info

# Dev
poetry run pytest                   # 151 tests
```

## Architecture

- **`cli.py`** — 18 CLI commands (init, migrate, start, chat, shutdown, status, doctor, config, logs, branches, diff, test, review, pipeline, agents, curls, setup, version, help)
- **`chat.py`** — Interactive REPL: agent picker menu, streaming, multi-turn sessions, `/agent` switching, inline agent delegation (`/<agent> <prompt>`), tab-completion, auto-detects git repo from cwd, auto-starts server
- **`setup.py`** — Interactive setup wizard
- **`env_loader.py`** — Centralized env loading: global (`~/.code-agents/config.env`) + per-repo (`.env.code-agents`)
- **`app.py`** — FastAPI app, CORS, lifespan, request/response logging
- **`backend.py`** — Backend abstraction: cursor CLI, cursor HTTP, claude (claude-agent-sdk built-in)
- **`stream.py`** — SSE streaming with ToolUse/ToolResult logging
- **`logging_config.py`** — Hourly rotating log files (7-day retention)
- **CI/CD clients**: `git_client.py`, `testing_client.py`, `jenkins_client.py`, `argocd_client.py`
- **CI/CD routers**: `routers/git_ops.py`, `testing.py`, `jenkins.py`, `argocd.py`, `pipeline.py`
- **`pipeline_state.py`** — 6-step state machine (connect → review/test → build → deploy → verify → rollback)
- **`agents/*.yaml`** — 12 agent definitions
- **`tests/`** — 151 tests

## Key Patterns

- **CLI entry**: `pyproject.toml` → `code-agents = "code_agents.cli:main"`
- **Centralized config**: `code-agents init` writes global config to `~/.code-agents/config.env` (API keys, server) and per-repo config to `.env.code-agents` (Jenkins, ArgoCD). Legacy `.env` still loaded for backward compat.
- **Interactive chat**: `code-agents chat` → numbered menu → REPL with streaming. `/agent` switches permanently. `/<agent> <prompt>` delegates one-shot to another agent. Tab-completion for commands and agent names. Each agent stays in role. Auto-detects git repo from cwd. Auto-starts server if not running.
- **Dynamic `repo_path`**: request param → `TARGET_REPO_PATH` env → `os.getcwd()` (never stored in config)
- **Background server**: `start` launches background process, `shutdown` kills it
- **Hourly log rotation**: `logs/code-agents.log` = last hour, 168 backups (7 days)
- **Agent names**: kebab-case in URLs, snake_case in filenames
- **Backends**: `"cursor"` (default) or `"claude"`, per agent. `claude-agent-sdk` is a core dependency; `cursor-agent-sdk` is optional.

## Environment Variables

Global (`~/.code-agents/config.env`):
- `CURSOR_API_KEY` / `ANTHROPIC_API_KEY` — Backend keys
- `HOST` / `PORT` — Server bind (default `0.0.0.0:8000`)
- `REDASH_*`, `ELASTICSEARCH_*`, `ATLASSIAN_*` — Integrations

Per-repo (`.env.code-agents`):
- `JENKINS_URL`, `JENKINS_USERNAME`, `JENKINS_API_TOKEN`, `JENKINS_BUILD_JOB`, `JENKINS_DEPLOY_JOB`
- `ARGOCD_URL`, `ARGOCD_AUTH_TOKEN`, `ARGOCD_APP_NAME`
- `TARGET_TEST_COMMAND`, `TARGET_COVERAGE_THRESHOLD`

Runtime (never stored): `TARGET_REPO_PATH` — auto-detected from cwd

## Testing

151 tests — `poetry run pytest`. Covers: chat REPL (slash commands, agent parsing, SSE streaming, repo detection, inline delegation, tab-completion), centralized env loading (split_vars, load order, var classification), CLI (all 18 commands, help completeness, config, curls, dispatcher), git operations, test framework detection, coverage XML, Jenkins/ArgoCD client init, all routers, pipeline lifecycle, health/diagnostics.

## Adding a New Agent

1. Create `agents/<name>.yaml`
2. Add to `agents/agent_router.yaml` system prompt
3. Add to `Agents.md`, `README.md`
4. Add role to `AGENT_ROLES` in `chat.py`
