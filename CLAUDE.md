# CLAUDE.md — Project Context for Claude Code

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
code-agents rules                   # manage agent rules (list/create/edit/delete)
code-agents restart                 # restart server (shutdown + start)
code-agents completions --install   # install shell tab-completion
code-agents migrate                 # migrate legacy .env to centralized config
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
poetry run pytest                   # 178 tests
poetry run python initiater/run_audit.py
```

## Architecture

- **`code_agents/cli.py`** — Unified CLI entry point: 21 commands (init, migrate, rules, start, restart, chat, shutdown, status, doctor, config, logs, branches, diff, test, review, pipeline, agents, curls, setup, version, completions, help)
- **`code_agents/chat.py`** — Interactive chat REPL: agent picker menu, streaming responses, multi-turn sessions, `/agent` switching, inline agent delegation (`/<agent> <prompt>`), tab-completion for slash commands and agent names, auto-detects git repo from cwd, auto-starts server if not running
- **`code_agents/setup.py`** — Interactive setup wizard (7 steps)
- **`code_agents/main.py`** — Uvicorn server launcher
- **`code_agents/app.py`** — FastAPI app, CORS, lifespan, extensive request/response logging middleware
- **`code_agents/config.py`** — `AgentConfig`, `Settings`, `AgentLoader` (reads YAML, expands `${ENV_VAR}`)
- **`code_agents/env_loader.py`** — Centralized env loading: global (`~/.code-agents/config.env`) + per-repo (`.env.code-agents`), variable classification, `load_all_env()`
- **`code_agents/rules_loader.py`** — Agent rules system: global (`~/.code-agents/rules/`) + project (`.code-agents/rules/`), per-agent targeting, auto-refresh on every message
- **`code_agents/backend.py`** — Backend abstraction: `run_agent()` dispatches to cursor CLI, cursor HTTP, or claude
- **`code_agents/stream.py`** — SSE streaming with ToolUse/ToolResult logging per request
- **`code_agents/models.py`** — Pydantic request/response models (OpenAI-compatible)
- **`code_agents/logging_config.py`** — Hourly rotating file handler (current = last hour, 7 days backup)
- **`code_agents/git_client.py`** — Async git subprocess wrapper
- **`code_agents/testing_client.py`** — Test runner + coverage XML parser (auto-detects pytest/jest/maven/gradle/go)
- **`code_agents/jenkins_client.py`** — Jenkins REST API client (trigger, poll, logs, CSRF crumb)
- **`code_agents/argocd_client.py`** — ArgoCD REST API client (status, pods, logs, sync, rollback)
- **`code_agents/pipeline_state.py`** — In-memory 6-step pipeline state machine
- **`code_agents/routers/`** — FastAPI route handlers: completions, agents_list, git_ops, testing, jenkins, argocd, pipeline, redash, elasticsearch, atlassian_oauth_web
- **`agents/*.yaml`** — 12 agent definitions
- **`tests/`** — 178 tests
- **`initiater/`** — Project quality audit system (14 rules)

## Key Patterns

- **CLI-first**: `code-agents init` writes global config to `~/.code-agents/config.env` and per-repo config to `.env.code-agents`. `code-agents start` loads both. `code-agents chat` opens REPL.
- **Interactive chat**: `code-agents chat` shows numbered agent menu → pick one → REPL with streaming. `/agent <name>` switches permanently. `/<agent> <prompt>` delegates one-shot to another agent without switching. Tab-completion for all slash commands and agent names. Each agent stays in its role. Auto-detects git repo from cwd and passes it as `cwd` to the agent. Auto-starts server if not running.
- **Dynamic `repo_path`**: Per-request `?repo_path=` → `TARGET_REPO_PATH` env → `os.getcwd()` fallback.
- **Background server**: `code-agents start` launches in background, shows URLs + curl commands. `code-agents shutdown` kills it.
- **Agent names**: kebab-case in URLs (`code-reasoning`), snake_case in filenames (`code_reasoning.yaml`).
- **`${VAR}` expansion** in YAML `api_key` and `system_prompt` fields.
- **Backends**: `"cursor"` (default) or `"claude"`. Each agent picks independently. `claude-agent-sdk` is a core dependency; `cursor-agent-sdk` is optional.
- **Permission modes**: `default` (ask), `acceptEdits` (auto-approve), `bypassPermissions` (read-only).
- **Agent rules**: Two-tier rules injected into system prompts. Global (`~/.code-agents/rules/`) + project (`{repo}/.code-agents/rules/`). `_global.md` = all agents, `{agent-name}.md` = specific agent. Auto-refresh on every message (no cache). Managed via `code-agents rules` CLI or `/rules` in chat.
- **Hourly log rotation**: `logs/code-agents.log` = last hour, 168 backups (7 days).

## Environment Variables

Key vars (see `.env.example` for full list):
- `CURSOR_API_KEY` / `ANTHROPIC_API_KEY` — Backend keys
- `HOST` / `PORT` — Server bind (default `0.0.0.0:8000`)
- `TARGET_REPO_PATH` — Auto-detected from cwd if empty
- `JENKINS_URL`, `JENKINS_USERNAME`, `JENKINS_API_TOKEN` — Jenkins CI/CD
- `JENKINS_BUILD_JOB`, `JENKINS_DEPLOY_JOB` — Job paths (not full URLs)
- `ARGOCD_URL`, `ARGOCD_AUTH_TOKEN`, `ARGOCD_APP_NAME` — ArgoCD

## Testing

- 178 tests in `tests/` — `poetry run pytest`
- `test_chat.py` (59): agent roles, `_get_agents` parsing, server check, slash commands, repo detection, SSE parsing, inline agent delegation, tab-completion, command extraction
- `test_env_loader.py` (21): split_vars classification, load_all_env order (global → legacy → per-repo), .env directory handling, var set overlap checks
- `test_rules_loader.py` (18): rules dir reading, load_rules merge order, agent targeting, auto-refresh, list_rules filtering
- `test_cli.py` (24): server URL, help completeness (all 21 cmds, slash cmds, agents), version, doctor, config, curls, dispatcher
- `test_git_client.py` (10): ref validation, branches, diff, log, status
- `test_jenkins_client.py` (5): Jenkins + ArgoCD client init
- `test_routers.py` (14): all FastAPI routers, pipeline lifecycle, health/diagnostics
- `test_testing_client.py` (18): test detection, coverage XML, pipeline state machine

## Adding a New Agent

1. Create `agents/<name>.yaml`
2. Add to `agents/agent_router.yaml` system prompt
3. Add to `Agents.md`, `README.md` agents table
4. Add role to `AGENT_ROLES` dict in `code_agents/chat.py`