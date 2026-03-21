# CLAUDE.md — Project Context for Claude Code

## What This Project Is

Code Agents is a YAML-driven OpenAI-compatible API server with a built-in CI/CD pipeline. It exposes 12 agents (coding, testing, review, git, Jenkins, ArgoCD, pipeline orchestration) as API endpoints. Users install once, run `code-agents init` in any repo, and get a full deployment platform.

## Quick Reference

```bash
# Install (one-time)
curl -fsSL https://raw.githubusercontent.com/shivanshu1gupta-paytmpayments/code-agents/main/install.sh | bash

# Initialize in a repo
cd /path/to/your-project
code-agents init                # configure keys, write .env

# Start server
code-agents start               # foreground
code-agents start --bg          # background

# CLI commands
code-agents help                # show all commands
code-agents status              # check server health
code-agents shutdown            # stop the server
code-agents doctor              # diagnose issues
code-agents agents              # list 12 agents
code-agents config              # show .env (secrets masked)
code-agents logs                # tail log file
code-agents branches            # list git branches
code-agents diff main HEAD      # show diff
code-agents test                # run tests
code-agents review main HEAD    # AI code review
code-agents pipeline start      # start CI/CD pipeline
code-agents pipeline status     # check pipeline

# Run tests
poetry run pytest               # 47 tests

# Run project audit
poetry run python initiater/run_audit.py
```

## Architecture

- **`agents/*.yaml`** — 12 YAML agent definitions loaded at startup by `config.py:AgentLoader`
- **`code_agents/`** — FastAPI Python package:
  - `cli.py` — Unified CLI entry point: `init`, `start`, `shutdown`, `status`, `diff`, `test`, `review`, `pipeline`, `doctor`, `config`, `logs`, `agents`, `branches`, `version`, `setup`, `help`
  - `setup.py` — Interactive setup wizard (prompts for keys, writes .env)
  - `main.py` — Uvicorn server launcher
  - `app.py` — FastAPI app, CORS, lifespan, extensive request/response logging
  - `config.py` — `AgentConfig` dataclass, `Settings`, `AgentLoader` (reads YAML, expands `${ENV_VAR}`)
  - `backend.py` — Backend abstraction: `run_agent()` dispatches to cursor CLI, cursor HTTP, or claude
  - `stream.py` — SSE streaming with tool activity logging (ToolUse/ToolResult tracked per request)
  - `models.py` — Pydantic request/response models (OpenAI-compatible)
  - `logging_config.py` — Hourly rotating file handler (current file = last hour, 7 days backup)
  - `git_client.py` — Async git subprocess wrapper (branches, diff, log, push, status)
  - `testing_client.py` — Test runner + coverage XML parser (auto-detects pytest/jest/maven/gradle/go)
  - `jenkins_client.py` — Jenkins REST API client (trigger, poll, logs, CSRF crumb)
  - `argocd_client.py` — ArgoCD REST API client (status, pods, logs, sync, rollback)
  - `pipeline_state.py` — In-memory 6-step pipeline state machine
  - `routers/` — FastAPI route handlers:
    - `completions.py` — `POST /v1/agents/{name}/chat/completions`
    - `agents_list.py` — `GET /v1/agents`, `GET /v1/models`
    - `git_ops.py` — `/git/*` (branches, diff, log, push, status, fetch)
    - `testing.py` — `/testing/*` (run, coverage, gaps)
    - `jenkins.py` — `/jenkins/*` (build, status, log, wait)
    - `argocd.py` — `/argocd/*` (status, pods, logs, sync, rollback, history)
    - `pipeline.py` — `/pipeline/*` (start, status, advance, fail, rollback, runs)
    - `redash.py`, `elasticsearch.py`, `atlassian_oauth_web.py`
- **`tests/`** — 47 tests covering all clients, routers, pipeline state, and validators
- **`initiater/`** — Project quality audit system (14 rule files + LLM runner)

## Key Patterns

- **CLI-first**: `code-agents init` in any repo writes `.env` there. `code-agents start` reads `.env` from cwd.
- **Dynamic `repo_path`**: Per-request `?repo_path=` → `TARGET_REPO_PATH` env → `os.getcwd()` fallback.
- **Agent names are kebab-case** in URLs (e.g., `code-reasoning`), **snake_case** in filenames (e.g., `code_reasoning.yaml`).
- **`${VAR}` expansion** works in YAML `api_key` and `system_prompt` fields.
- **Backends**: `"cursor"` (default) or `"claude"`. Each agent picks independently.
- **Permission modes**: `default` (ask), `acceptEdits` (auto-approve), `bypassPermissions` (read-only).
- **Background server**: `code-agents init` and `code-agents start --bg` launch as background process.
- **Hourly log rotation**: `logs/code-agents.log` has only the last hour, backups kept for 7 days.

## Adding a New Agent — Required Updates

1. Create `agents/<name>.yaml`
2. Add to `agents/agent_router.yaml` system prompt (specialists list)
3. Add to `README.md`: Included Agents table, Project Structure tree
4. Add to `Agents.md` with its own section

## Environment Variables

Key vars (see `.env.example` for full list):
- `CURSOR_API_KEY` — Required for cursor backend
- `CURSOR_API_URL` — Optional; enables HTTP mode
- `ANTHROPIC_API_KEY` — Required for claude backend
- `HOST` / `PORT` — Server bind (default `0.0.0.0:8000`)
- `TARGET_REPO_PATH` — Target repo (auto-detected from cwd if empty)
- `JENKINS_URL`, `JENKINS_USERNAME`, `JENKINS_API_TOKEN` — Jenkins CI/CD
- `JENKINS_BUILD_JOB`, `JENKINS_DEPLOY_JOB` — Job paths (not full URLs)
- `ARGOCD_URL`, `ARGOCD_AUTH_TOKEN`, `ARGOCD_APP_NAME` — ArgoCD

## Testing

- 47 tests in `tests/` — run with `poetry run pytest`
- Covers: git client (real temp repos), testing client (auto-detection, coverage XML parsing), Jenkins/ArgoCD client init, all routers (FastAPI TestClient), pipeline state machine lifecycle, health/diagnostics endpoints

## Code Style

- Python 3.10+ with type hints
- FastAPI + Pydantic v2
- `from __future__ import annotations` used in most modules
- Async handlers throughout (`async def`)
- Extensive logging: every request, every git command, every tool use, every pipeline state transition
