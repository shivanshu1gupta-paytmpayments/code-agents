# Cursor Rules — Project Context for Cursor AI

## What This Project Is

Code Agents is a YAML-driven OpenAI-compatible API server with a built-in CI/CD pipeline. It exposes 12 agents as API endpoints and provides a CLI (`code-agents`) for installation, configuration, and operation.

## Quick Reference

```bash
# Install (one-time)
curl -fsSL https://raw.githubusercontent.com/shivanshu1gupta-paytmpayments/code-agents/main/install.sh | bash

# Per-repo setup
cd /path/to/your-project
code-agents init                # configure keys, write .env
code-agents start               # start server (foreground)
code-agents start --bg          # start server (background)
code-agents shutdown            # stop the server

# Useful commands
code-agents help                # all commands
code-agents status              # health check
code-agents doctor              # diagnose issues
code-agents agents              # list 12 agents
code-agents diff main HEAD      # git diff
code-agents test                # run tests
code-agents review main HEAD    # AI code review
code-agents pipeline start      # start CI/CD pipeline

# Dev
poetry run pytest               # 47 tests
poetry run python initiater/run_audit.py --rules workflow
```

## Architecture

- **`code_agents/cli.py`** — Unified CLI: `init`, `start`, `shutdown`, `status`, `diff`, `test`, `review`, `pipeline`, `doctor`, `config`, `logs`, `agents`, `branches`, `version`, `setup`, `help`
- **`code_agents/setup.py`** — Interactive setup wizard
- **`code_agents/app.py`** — FastAPI app, CORS, lifespan, request/response logging middleware
- **`code_agents/backend.py`** — Backend abstraction: cursor CLI, cursor HTTP, claude
- **`code_agents/stream.py`** — SSE streaming with ToolUse/ToolResult logging
- **`code_agents/logging_config.py`** — Hourly rotating log files (7-day retention)
- **`agents/*.yaml`** — 12 agent definitions
- **CI/CD clients**: `git_client.py`, `testing_client.py`, `jenkins_client.py`, `argocd_client.py`
- **CI/CD routers**: `routers/git_ops.py`, `routers/testing.py`, `routers/jenkins.py`, `routers/argocd.py`, `routers/pipeline.py`
- **`pipeline_state.py`** — 6-step state machine (connect → review/test → build → deploy → verify → rollback)
- **`tests/`** — 47 tests

## Key Patterns

- **CLI entry point**: `pyproject.toml` → `code-agents = "code_agents.cli:main"`
- **Per-repo .env**: `code-agents init` writes `.env` in the current directory. `code-agents start` reads from cwd.
- **Dynamic `repo_path`**: Request param → `TARGET_REPO_PATH` env → `os.getcwd()` fallback
- **Agent names**: kebab-case in URLs (`code-reasoning`), snake_case in filenames (`code_reasoning.yaml`)
- **`${VAR}` expansion** in YAML `api_key` and `system_prompt` fields
- **Backends**: `"cursor"` (default) or `"claude"`, per agent
- **Permission modes**: `default`, `acceptEdits`, `bypassPermissions`
- **Background server**: `init` and `start --bg` launch as subprocess, show clean URL summary
- **Hourly log rotation**: `logs/code-agents.log` = last hour only, 168 backup files (7 days)

## Environment Variables

Key vars (`.env.example` has full list):
- `CURSOR_API_KEY` / `ANTHROPIC_API_KEY` — Backend keys
- `HOST` / `PORT` — Server bind (default `0.0.0.0:8000`)
- `TARGET_REPO_PATH` — Auto-detected from cwd
- `JENKINS_URL`, `JENKINS_USERNAME`, `JENKINS_API_TOKEN`, `JENKINS_BUILD_JOB`, `JENKINS_DEPLOY_JOB`
- `ARGOCD_URL`, `ARGOCD_AUTH_TOKEN`, `ARGOCD_APP_NAME`

## Testing

- 47 tests — `poetry run pytest`
- Covers: git operations (real temp repos), test framework detection, coverage XML parsing, Jenkins/ArgoCD client init, all FastAPI routers, pipeline lifecycle, health/diagnostics

## Things to Watch Out For

- `agent_router.yaml` system prompt must list ALL 12 specialist agents
- `stream_tool_activity` sends tool calls via `reasoning_content` — not all clients render this
- Session IDs are backend-managed (cursor-agent or claude), not server-side
- `.env` is loaded from cwd in `cli.py` and from project root in `app.py` lifespan
- Jenkins `JENKINS_BUILD_JOB` should be a path (`pg2/pg2-dev-build-jobs`), NOT a full URL
- `code-agents shutdown` kills the process on the configured port
