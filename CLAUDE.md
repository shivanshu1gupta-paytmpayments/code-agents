# CLAUDE.md — Project Context for Claude Code

## What This Project Is

Code Agents is a YAML-driven OpenAI-compatible API server that exposes cursor-agent and claude-agent as API endpoints. Users define agents in YAML, run the server, and connect from any OpenAI-compatible client (e.g., Open WebUI).

## Quick Reference

```bash
# Install
poetry install

# Run server
poetry run code-agents            # default: 0.0.0.0:8000
HOST=127.0.0.1 PORT=9000 poetry run code-agents

# Run tests
poetry run pytest

# Run project audit
poetry run python initiater/run_audit.py
poetry run python initiater/run_audit.py --rules workflow,documentation

# Verify running server
curl -s http://localhost:8000/diagnostics | python3 -m json.tool
```

## Architecture

- **`agents/*.yaml`** — Each YAML file defines one agent (name, backend, model, system prompt, permissions). Loaded at startup by `config.py:AgentLoader`.
- **`code_agents/`** — FastAPI Python package:
  - `app.py` — FastAPI app, CORS, lifespan, exception handlers
  - `config.py` — `AgentConfig` dataclass, `Settings`, `AgentLoader` (reads YAML, expands `${ENV_VAR}`)
  - `backend.py` — Backend abstraction: `run_agent()` dispatches to cursor CLI, cursor HTTP, or claude
  - `stream.py` — SSE streaming, response builders
  - `models.py` — Pydantic request/response models (OpenAI-compatible)
  - `routers/completions.py` — `POST /v1/agents/{name}/chat/completions`
  - `routers/agents_list.py` — `GET /v1/agents`, `GET /v1/models`
- **`initiater/`** — Project quality audit system (rule files + LLM runner)

## Key Patterns

- **Agent names are kebab-case** in URLs and YAML `name` field (e.g., `code-reasoning`), **snake_case** in filenames (e.g., `code_reasoning.yaml`).
- **`${VAR}` expansion** works in YAML `api_key` and `system_prompt` fields, resolved from environment at load time.
- **Two cursor modes**: CLI (`cursor-agent` subprocess) and HTTP (`CURSOR_API_URL` → OpenAI-compatible endpoint). Backend selection is automatic based on whether `CURSOR_API_URL` is set.
- **Backends**: `"cursor"` (default) or `"claude"`. Each agent picks independently.
- **Permission modes**: `default` (ask), `acceptEdits` (auto-approve writes), `bypassPermissions` (read-only).

## Adding a New Agent — Required Updates

When adding a new agent, **all of these must be updated in sync**:

1. Create `agents/<name>.yaml`
2. Add to `agents/agent_router.yaml` system prompt (specialists list)
3. Add to `README.md`: Included Agents table, Option B table, Project Structure tree
4. Add to `Agents.md` with its own section

Run `poetry run python initiater/run_audit.py --rules workflow` to verify sync.

## Environment Variables

Key vars (see `.env.example` for full list):
- `CURSOR_API_KEY` — Required for cursor backend
- `CURSOR_API_URL` — Optional; enables HTTP mode (no Cursor desktop app needed)
- `ANTHROPIC_API_KEY` — Required for claude backend
- `HOST` / `PORT` — Server bind address (default `0.0.0.0:8000`)
- `AGENTS_DIR` — Custom agents directory (default `./agents`)

## Testing

- No test suite exists yet — this is a known gap
- `pytest` is configured as a dev dependency
- Integration testing: use `curl` against running server or `scripts/verify-server.sh`

## Code Style

- Python 3.10+ with type hints
- FastAPI + Pydantic v2
- `from __future__ import annotations` used in most modules
- Async handlers throughout (`async def`)

## Things to Watch Out For

- The `agent_router.yaml` system prompt must list ALL specialist agents — it's easy to forget when adding new ones
- `stream_tool_activity` sends tool calls via `reasoning_content` in SSE chunks — not all clients render this
- Session IDs are backend-managed (cursor-agent or claude), not server-side
- `.env` is loaded in `app.py` lifespan AND `main.py` — both paths must work
