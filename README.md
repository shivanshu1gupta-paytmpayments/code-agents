# Code Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

YAML-driven OpenAI-compatible API server that exposes [cursor-agent](https://cursor.com/docs/cli) and [claude-agent](https://docs.anthropic.com/en/docs/agents/claude-agent-sdk) as API endpoints. Define agents in YAML, run the server, and connect from any OpenAI-compatible client — including [Open WebUI](https://github.com/open-webui/open-webui).

## What is this?

Code Agents lets you:

- **Define coding agents in YAML** — system prompt, model, backend, permissions — all configurable without code changes
- **Expose them as OpenAI-compatible endpoints** — any client that speaks the OpenAI API can use your agents
- **Use Cursor or Claude as the backend** — swap between `cursor-agent` and `claude-agent` per agent
- **Stream tool activity** — see what tools the agent is using (file reads, writes, searches) in real-time via `reasoning_content`
- **Manage sessions** — resume multi-turn conversations using session IDs

## Quick Start

### Prerequisites

- Python 3.10+
- [cursor-agent CLI](https://cursor.com/docs/cli): `curl https://cursor.com/install -fsS | bash`
- Active Cursor subscription (or Anthropic API key for claude backend)
- Optional — browser chat UI: [Open WebUI](https://github.com/open-webui/open-webui) needs **Python 3.11 or 3.12** (not 3.13+ yet). See [Running Open WebUI without Docker](#running-open-webui-without-docker).

### Install

```bash
git clone https://github.com/YOUR_USERNAME/code-agents.git
cd code-agents

# Install with Poetry (main dependencies only — no cursor-agent-sdk)
poetry install

# Cursor CLI backend (`backend: cursor` without CURSOR_API_URL): add the SDK
poetry install --with cursor

# Or with pip
pip install .

# Cursor CLI backend: also install the SDK from git, e.g.
# pip install git+https://github.com/gitcnd/cursor-agent-sdk-python.git

# Environment (keys and optional headless Cursor HTTP base)
cp .env.example .env
# Edit .env: set CURSOR_API_KEY; add CURSOR_API_URL if you are not running the Cursor desktop app (see README).
```

### Run

```bash
# Start the server (default: 0.0.0.0:8000)
poetry run code-agents

# Or directly
poetry run python -m code_agents.main

# Custom host/port
HOST=127.0.0.1 PORT=9000 poetry run code-agents
```

### Test

```bash
# List available agents
curl http://localhost:8000/v1/agents

# Send a prompt (non-streaming)
curl -X POST http://localhost:8000/v1/agents/code-reasoning/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is a Python decorator?"}]}'

# Streaming: use -N so curl doesn't buffer (avoids "transfer closed" errors)
curl -N -X POST http://localhost:8000/v1/agents/code-reasoning/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is a Python decorator?"}], "stream": true}'
```

### Verify the running server (troubleshooting)

If something “reproduces” but traces look **old** (e.g. missing files or line numbers that don’t match your tree), confirm **which** process you hit:

```bash
# Should show package_version, backend_py (path to this repo’s code_agents/backend.py), and agent list
curl -s http://localhost:8000/diagnostics | python3 -m json.tool
```

Or run **`scripts/verify-server.sh`** (optional: `CODE_AGENTS_URL=http://127.0.0.1:9000 ./scripts/verify-server.sh`).

### Atlassian MCP (Jira / Confluence) from Python

This repo includes **Atlassian OAuth 2.0 (3LO)** examples (same **browser login → authorize → callback** model as the **Cursor Atlassian** flow): **`examples/atlassian_mcp_client.py`** (CLI opens the browser) and **`examples/atlassian_oauth_server.py`** (small FastAPI “Sign in with Atlassian” page). Tokens are used with **Atlassian Rovo MCP** (`https://mcp.atlassian.com/v1/mcp`). Configure an OAuth app in the [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/) (callback URL must match the flow you use), set `ATLASSIAN_OAUTH_CLIENT_ID`, `ATLASSIAN_OAUTH_CLIENT_SECRET`, and `ATLASSIAN_OAUTH_SCOPES`, then see **`examples/README-atlassian-mcp.md`**. (These are **Atlassian** credentials — not your Cursor API key.)

**HTTPS / TLS when exchanging the OAuth code:** Token exchange calls `https://auth.atlassian.com`. If you see **`CERTIFICATE_VERIFY_FAILED`** (common behind corporate TLS inspection), set **`SSL_CERT_FILE`** or **`REQUESTS_CA_BUNDLE`** to a PEM bundle that trusts your inspection root, or set **`CODE_AGENTS_HTTPS_VERIFY=0`** (**insecure**; local troubleshooting only). Details: **`examples/README-atlassian-mcp.md`** and [Troubleshooting](#troubleshooting) → Atlassian OAuth.

## Creating Agents

Drop a YAML file in the `agents/` directory and restart the server. Each file defines one agent.

### Example

```yaml
# agents/my_agent.yaml
name: my-agent
display_name: "My Custom Agent"
backend: cursor
model: "composer-1.5"
system_prompt: |
  You are a helpful coding assistant. You analyze code,
  answer questions, and suggest improvements.
permission_mode: default
api_key: ${CURSOR_API_KEY}
cwd: "."
stream_tool_activity: true
include_session: true
extra_args:
  mode: ask
```

The agent is available at `POST /v1/agents/my-agent/chat/completions`.

### Included Agents

| Agent | Description | Permissions |
|---|---|---|
| `agent-router` | Primary entry point: asks what you need and recommends which specialist (`code-reasoning`, `code-writer`, `code-reviewer`, `code-tester`, `redash-query`) and endpoint | Read-only (`mode: ask`) |
| `code-reasoning` | Analyzes codebases, explains architecture, traces data flows | Read-only (`mode: ask`) |
| `code-writer` | Generates and modifies code based on requirements | Auto-approves edits (`acceptEdits`) |
| `code-reviewer` | Reviews code for bugs, security issues, and style | Read-only (`mode: ask`) |
| `code-tester` | Tests codebases, writes tests, debugs and optimizes code | Auto-approves edits (`acceptEdits`) |
| `redash-query` | Queries databases via Redash: explores schemas, writes SQL from natural language, executes and explains results | Read-only (`mode: ask`) |
| `git-ops` | Git operations on target repo: branches, diffs, logs, push | Read-only (`mode: ask`) |
| `test-coverage` | Runs tests, generates coverage, identifies coverage gaps in new code | Auto-approves edits (`acceptEdits`) |
| `jenkins-build` | Triggers and monitors Jenkins CI build jobs | Read-only (`mode: ask`) |
| `jenkins-deploy` | Triggers and monitors Jenkins deployment jobs | Read-only (`mode: ask`) |
| `argocd-verify` | Verifies ArgoCD deployments, scans pod logs, rollbacks | Read-only (`mode: ask`) |
| `pipeline-orchestrator` | Full CI/CD pipeline: connect → review → test → build → deploy → verify → rollback | Read-only (`mode: ask`) |

### YAML Configuration Reference

| Field | Required | Default | Description |
|---|---|---|---|
| `name` | yes | — | URL-safe identifier used in the endpoint path |
| `display_name` | no | same as `name` | Human-readable name shown in listings |
| `backend` | no | `"cursor"` | Backend engine: `"cursor"` or `"claude"` |
| `model` | no | `"composer 1.5"` | Default LLM model for this agent |
| `system_prompt` | no | `""` | System prompt prepended to every conversation |
| `permission_mode` | no | `"default"` | `"default"`, `"acceptEdits"`, or `"bypassPermissions"` |
| `cwd` | no | `"."` | Working directory for the agent |
| `api_key` | no | env fallback | API key; supports `${ENV_VAR}` syntax for env variable injection |
| `stream_tool_activity` | no | `true` | Show tool calls/results in `reasoning_content` |
| `include_session` | no | `true` | Include `session_id` in responses |
| `extra_args` | no | `{}` | Additional CLI arguments (e.g. `mode: ask`) |

### Environment Variable Injection

API keys support `${VAR_NAME}` syntax — the value is resolved from the environment at startup:

```yaml
api_key: ${CURSOR_API_KEY}      # For cursor backend
api_key: ${ANTHROPIC_API_KEY}   # For claude backend
```

If `api_key` is not set in YAML, the server falls back to reading the environment variable directly.

**`system_prompt` placeholders:** You can use `${VAR_NAME}` in `system_prompt` (same pattern as `api_key`). Values come from the environment when agents load (after `.env` is applied). If unset, `${CODE_AGENTS_PUBLIC_BASE_URL}` defaults to `http://127.0.0.1:<server port>` and `${ATLASSIAN_CLOUD_SITE_URL}` defaults to a short reminder to set it in `.env` — useful for **agent-router** text that points users at `/oauth/atlassian/`.

## API Endpoints

### Chat Completions

```
POST /v1/agents/{agent_name}/chat/completions
```

OpenAI-compatible chat completion endpoint. Supports both streaming and non-streaming responses.

**Request body:**

| Field | Type | Default | Description |
|---|---|---|---|
| `messages` | array | required | OpenAI-format message array |
| `model` | string | agent default | LLM model override |
| `stream` | bool | `false` | Enable SSE streaming |
| `session_id` | string | `null` | Resume a previous session |
| `include_session` | bool | agent default | Include `session_id` in response |
| `stream_tool_activity` | bool | agent default | Show tool activity in `reasoning_content` |
| `cwd` | string | agent default | Working directory override |

**Response** (non-streaming):

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "model": "composer 1.5",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Here is my analysis...",
      "reasoning_content": "> **Using tool: Read**\n> ..."
    },
    "finish_reason": "stop"
  }],
  "session_id": "310a655d-8f06-4bb0-9bb6-89d33be5589c"
}
```

**Response** (streaming): Standard SSE `text/event-stream` with `chat.completion.chunk` objects. Tool activity appears in `reasoning_content` deltas.

### List Agents

```
GET /v1/agents
```

Returns all loaded agents with their configuration and endpoint URLs.

### List Models

```
GET /v1/models
```

OpenAI-compatible model listing. Each agent is exposed as a "model" for compatibility with clients that use the models endpoint.

### Health Check

```
GET /health
```

### Redash integration (run DB queries)

You can run database queries through [Redash](https://redash.io/) using either an API key or username/password.

**Environment variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `REDASH_BASE_URL` | yes | Redash base URL (e.g. `https://redash.example.com`) |
| `REDASH_API_KEY` | * | User or query API key (recommended). Find it in Redash under your profile. |
| `REDASH_USERNAME` | * | Login email (use with `REDASH_PASSWORD` for session auth) |
| `REDASH_PASSWORD` | * | Login password |

Set either `REDASH_API_KEY` or both `REDASH_USERNAME` and `REDASH_PASSWORD`.

**Endpoints:**

- **Run ad-hoc query** — execute a query against a Redash data source:
  ```
  POST /redash/run-query
  Content-Type: application/json

  {
    "data_source_id": 1,
    "query": "SELECT * FROM users LIMIT 10",
    "max_age": 0,
    "parameters": {}
  }
  ```
  Response: `{ "columns": [...], "rows": [...], "metadata": { "runtime", "row_count" } }`

- **Run saved query** — execute a saved Redash query by ID:
  ```
  POST /redash/run-saved-query
  Content-Type: application/json

  { "query_id": 123, "max_age": 0, "parameters": {} }
  ```

- **List data sources** — get data source IDs for `run-query`:
  ```
  GET /redash/data-sources
  ```

- **Get schema** — tables and columns for a data source:
  ```
  GET /redash/data-sources/{data_source_id}/schema
  ```

### Elasticsearch integration

Connect to Elasticsearch or Elastic Cloud with the official Python client (`elasticsearch` 8.x). Set `ELASTICSEARCH_URL` or `ELASTICSEARCH_CLOUD_ID`, plus `ELASTICSEARCH_API_KEY` or `ELASTICSEARCH_USERNAME` / `ELASTICSEARCH_PASSWORD`. See `.env.example`.

**Endpoints:**

- `GET /elasticsearch/info` — cluster info (connectivity check).
- `POST /elasticsearch/search` — JSON body: `{ "index": "*", "body": { "query": { "match_all": {} }, "size": 10 } }`.

`/diagnostics` includes `elasticsearch_configured` when URL or cloud id is set.

## Session Management

The server returns a `session_id` with each response. Pass it back to resume the conversation:

```bash
# First request
RESPONSE=$(curl -s -X POST http://localhost:8000/v1/agents/code-reasoning/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What files are in this project?"}]}')

SESSION_ID=$(echo $RESPONSE | jq -r '.session_id')

# Follow-up with session context
curl -X POST http://localhost:8000/v1/agents/code-reasoning/chat/completions \
  -H "Content-Type: application/json" \
  -d "{
    \"messages\": [{\"role\": \"user\", \"content\": \"Now explain main.py\"}],
    \"session_id\": \"$SESSION_ID\"
  }"
```

## Open WebUI Integration

Code Agents works as a custom OpenAI-compatible provider in [Open WebUI](https://github.com/open-webui/open-webui):

1. Start the Code Agents server
2. In Open WebUI, go to **Settings > Connections > OpenAI**
3. Add a connection (see options below)
4. Chat; tool activity appears in `reasoning_content`

**Model id in requests (e.g. `code-reasoning`)** only selects **which agent** to run. The **backend model** sent to cursor-agent / Claude is always the YAML **`model`** field (e.g. `composer-1.5`), not the Open WebUI model name—so you won’t see errors like *Cannot use this model: code-reasoning* from a correct setup.

### Open WebUI: add connection and models (step-by-step)

1. Start **Code Agents** first (`poetry run code-agents` on port **8000** by default).
2. In Open WebUI, open **Settings** (profile/gear icon) → **Connections** → **OpenAI** (wording may be **Admin settings** → **Connections** on some versions).
3. **Add connection** (or **Manage** → **Add**):
   - **Connection name**: any label, e.g. `Code Agents`.
   - **API Base URL** (must include `/v1`):
     - Open WebUI **on the same machine** as Code Agents: `http://localhost:8000/v1`
     - Open WebUI **inside Docker** while Code Agents runs on the host: use your platform’s host URL, e.g. `http://host.docker.internal:8000/v1` (macOS/Windows Docker Desktop) or the host LAN IP — **not** `http://localhost:8000/v1` from inside the container (that points at the container itself).
   - **API Key**: any non-empty string, e.g. `code-agents` (Code Agents does not validate it).
4. Save the connection. Open WebUI should call **`GET /v1/models`** on your server and list agents (`agent-router`, `code-reasoning`, `code-reviewer`, `code-writer`, plus any custom YAML agents). Pick one in the **model** dropdown before chatting. After you add a new YAML agent, **restart Code Agents** and use **refresh models** (or re-save the connection) so the new model appears.
5. If models do not appear, use **Option A** below and type or select the **model id** manually: it must match the agent **`name`** in `agents/*.yaml` (see `GET http://localhost:8000/v1/agents`).

**Custom agents**: add `agents/my_tool.yaml`, restart Code Agents, then refresh the connection or pick **`my-tool`** (or whatever `name:` you used) as the model. **Custom URL per agent** (one model per connection): use **Option B** and set the base URL to `http://localhost:8000/v1/agents/<agent_name>` (no trailing slash after the agent name).

Tool and step output from Code Agents is exposed in **`reasoning_content`** in the API; Open WebUI may show it depending on theme/settings—use **curl** or browser devtools if you need to confirm raw streams while iterating.

### Atlassian sign-in (same host as Open WebUI)

Open WebUI does **not** embed Atlassian OAuth inside its UI. This server can expose a **browser sign-in page on the same origin** as the API so you can authorize once, then use **`examples/atlassian_mcp_client.py`** or other tools that read the shared token cache.

1. Set **`ATLASSIAN_OAUTH_CLIENT_ID`**, **`ATLASSIAN_OAUTH_CLIENT_SECRET`**, and **`ATLASSIAN_OAUTH_SCOPES`** in `.env` (see **`examples/README-atlassian-mcp.md`**).
2. **Two different URLs** (do not confuse them):
   - **OAuth redirect / Open WebUI API** — must point at **this Code Agents server** (e.g. `http://127.0.0.1:8000` or a tunnel). Set **`CODE_AGENTS_PUBLIC_BASE_URL`** if the public URL differs from localhost. Register **`{CODE_AGENTS_PUBLIC_BASE_URL}/oauth/atlassian/callback`** in the [Developer Console](https://developer.atlassian.com/console/myapps/) — **not** your `*.atlassian.net` site.
   - **Atlassian Cloud site** (Jira/Confluence only) — e.g. **`https://paytmpayments.atlassian.net`**. Set **`ATLASSIAN_CLOUD_SITE_URL`** so `/oauth/atlassian/` shows the link; it is **not** the OAuth callback host.
3. Restart Code Agents, then open **`{CODE_AGENTS_PUBLIC_BASE_URL}/oauth/atlassian/`** (default `http://127.0.0.1:8000/oauth/atlassian/`), click **Sign in with Atlassian**, complete consent.
4. If the callback fails with **certificate verify failed** when talking to `auth.atlassian.com`, set **`SSL_CERT_FILE`** (or **`REQUESTS_CA_BUNDLE`**) to your CA bundle, or **`CODE_AGENTS_HTTPS_VERIFY=0`** / **`ATLASSIAN_OAUTH_HTTPS_VERIFY=0`** for dev-only (see env table in **`examples/README-atlassian-mcp.md`**).
5. `GET /diagnostics` includes **`code_agents_public_base_url`**, **`openai_api_base_url`**, **`atlassian_cloud_site_url`**, and **`atlassian_oauth_sign_in`** when relevant.

Chat in Open WebUI still **only** uses Cursor/claude agents via `/v1`; Confluence/Jira access is via separate scripts or your own integration that uses the saved OAuth token.

If the browser hits the callback twice after an error, you may get **invalid or expired state** — start again from **`/oauth/atlassian/`** (OAuth codes are single-use).

**If Cursor IDE crashes when Atlassian redirects back:** do OAuth in a **normal browser tab** (Safari/Chrome/Firefox) at **`http://127.0.0.1:8000/oauth/atlassian/`** — not Cursor’s Simple Browser, not a preview panel. Set **`OPEN_WEBUI_PUBLIC_URL=http://localhost:8080`** in `.env` (optional) so the success page links to chat — **`./scripts/start-with-open-webui.sh` sets this by default**. If you use **Cursor’s Atlassian MCP** as well, try signing in only in one place at a time to avoid conflicting OAuth flows.

### Option A: One connection (recommended)

- **URL**: `http://localhost:8000/v1`
- **API Key**: any non-empty string (e.g. `code-agents`)
- All agents (Agent Router, Code Reasoning, Code Reviewer, Code Writer, and any custom YAML agents) appear as models in the dropdown. Pick the model in the chat UI.

Use this single connection for normal prompting.

### Option B: Three separate connections (one per agent)

Use a **different API base URL per agent** so each connection has a single, clear purpose:

| Connection name (suggested) | URL | Use for |
|----------------------------|-----|--------|
| **Agent Router** | `http://localhost:8000/v1/agents/agent-router` | Triage: which specialist to use; does not replace the specialists |
| **Code Reasoning** | `http://localhost:8000/v1/agents/code-reasoning` | Analyze code, explain architecture, trace flows |
| **Code Reviewer** | `http://localhost:8000/v1/agents/code-reviewer` | Review code for bugs, security, style |
| **Code Writer** | `http://localhost:8000/v1/agents/code-writer` | Generate and edit code from requirements |
| **Code Tester** | `http://localhost:8000/v1/agents/code-tester` | Test codebases, write tests, debug and optimize code |
| **Redash Query** | `http://localhost:8000/v1/agents/redash-query` | Query databases via Redash, explore schemas, write SQL |
| **Git Ops** | `http://localhost:8000/v1/agents/git-ops` | Git operations on target repo |
| **Test Coverage** | `http://localhost:8000/v1/agents/test-coverage` | Run tests and check coverage |
| **Jenkins Build** | `http://localhost:8000/v1/agents/jenkins-build` | Trigger and monitor Jenkins builds |
| **Jenkins Deploy** | `http://localhost:8000/v1/agents/jenkins-deploy` | Trigger Jenkins deployments |
| **ArgoCD Verify** | `http://localhost:8000/v1/agents/argocd-verify` | Verify deployments and rollback |
| **Pipeline Orchestrator** | `http://localhost:8000/v1/agents/pipeline-orchestrator` | Full CI/CD pipeline end-to-end |

- **API Key**: any non-empty string for each (e.g. `code-agents`).
- Each connection exposes exactly one model, so you pick the right “endpoint” by choosing the connection. **Add a row for every agent you use** — e.g. `agent-router` is not included unless you add that URL.

No new models or separate backends are required—each URL is a different view of the same Code Agents server (same agents as in `GET /v1/agents`).

### Running Open WebUI without Docker

If your environment does not allow Docker, install Open WebUI with **Python 3.11 or 3.12**. The upstream package declares `Requires-Python < 3.13`, so **pipx** or **pip** using the default **Python 3.13+** interpreter will fail to resolve `open-webui`.

**Recommended (isolated CLI, same as `pip install` but avoids polluting your environment):**

```bash
pipx install open-webui --python python3.12
```

Use `python3.11` instead if that is what you have. Upgrade/reinstall later with the same `--python` flag so pipx does not recreate the venv with 3.13.

**Alternative (pip in a dedicated venv):**

```bash
python3.12 -m venv .venv-open-webui
source .venv-open-webui/bin/activate   # Windows: .venv-open-webui\Scripts\activate
pip install open-webui
```

This is optional tooling only — it is **not** installed by `poetry install`.

2. **Start Open WebUI** (after install — use the browser for chat):
   ```bash
   open-webui serve
   ```
   Open WebUI will be available at **http://localhost:8080**. Use the browser for all chat.

3. **Start Code Agents** in a separate terminal (or use the script below), then in Open WebUI add the connection as above with URL `http://localhost:8000/v1`.

To start both servers with one command, run from the project root:
   ```bash
   ./scripts/start-with-open-webui.sh
   ```
   The script **exports `OPEN_WEBUI_PUBLIC_URL=http://localhost:8080`** (or uses your `.env` value) **before** starting Code Agents, so **`/oauth/atlassian/`** “Signed in” links point at Open WebUI without extra `.env` setup. Override `OPEN_WEBUI_PUBLIC_URL` in `.env` if chat runs on another host/port.
   Unless you set **`ATLASSIAN_OAUTH_SUCCESS_REDIRECT`** in `.env`, the script also sets it to the same origin so a **successful** Atlassian login **302-redirects** the browser back to Open WebUI. Use `ATLASSIAN_OAUTH_SUCCESS_REDIRECT=` (empty) in `.env` if you prefer the HTML success page.

   Then open **http://localhost:8080** in your browser to chat; no need to use the terminal again.

## Cursor API only — without the Cursor desktop app

If you want **Cursor’s official HTTP API** and **no Cursor desktop IDE**, use what Cursor actually exposes today:

| What you need | How |
|----------------|-----|
| **Team admin, analytics, usage** | [Cursor APIs overview](https://cursor.com/docs/api) — `https://api.cursor.com`, **Basic auth** (`curl -u YOUR_API_KEY:`). Keys from dashboard (Admin / Analytics keys as documented). |
| **AI work on a GitHub repo (no desktop)** | [Cloud Agents API](https://cursor.com/docs/cloud-agent/api/endpoints.md) — `POST https://api.cursor.com/v0/agents` with `prompt`, `source.repository`, optional `model`. Key from **Dashboard → Cloud Agents**. This is **async, repo-based** (launch agent, poll status, read conversation) — not the same as a single “chat completion” in Open WebUI. |

**What Cursor does *not* publish (as of these docs):** a public **OpenAI-compatible** `POST …/chat/completions` endpoint that replaces **cursor-agent** for arbitrary local prompts with only `CURSOR_API_KEY`. This **code-agents** server uses the **cursor-agent** CLI for that style of chat; in many setups that CLI still expects the desktop app’s local proxy.

So:

- **“Cursor API only, no desktop”** for **repo automation** → use **Cloud Agents API** directly (or your own client), not necessarily this repo.
- **“Open WebUI + same experience as local Composer chat”** with **only** an API key and **no** desktop → **not supported** by Cursor’s documented HTTP APIs today; you’d need Cursor to ship a direct chat API or a headless cursor-agent path that never uses the desktop proxy.

## Using the Claude Backend

To use Claude instead of Cursor for an agent:

1. Install the claude dependency:
   ```bash
   poetry install --with claude
   ```

2. Set your API key:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

3. Create an agent YAML with `backend: claude`:
   ```yaml
   name: claude-coder
   backend: claude
   model: "sonnet"
   api_key: ${ANTHROPIC_API_KEY}
   ```

4. Restart the server

You can run cursor and claude agents simultaneously — each YAML file is independent.

A disabled example is included at `agents/claude_example.yaml.disabled`. Rename it to `.yaml` to activate.

## Docker

### Build

```bash
docker build -t code-agents .
```

### Run

```bash
# Basic
docker run -p 8000:8000 -e CURSOR_API_KEY=your-key code-agents

# Mount a workspace for agents to access
docker run -p 8000:8000 \
  -e CURSOR_API_KEY=your-key \
  -v /path/to/your/code:/workspace \
  code-agents

# Custom agents directory
docker run -p 8000:8000 \
  -e CURSOR_API_KEY=your-key \
  -e AGENTS_DIR=/app/agents \
  -v ./my-agents:/app/agents \
  code-agents
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `AGENTS_DIR` | `./agents` | Path to agent YAML directory |
| `CURSOR_API_KEY` | — | API key for cursor backend (CLI or HTTP path) |
| `CURSOR_API_URL` | — | Optional. If set, `backend: cursor` agents use **HTTP** `POST {URL}/chat/completions` with `Authorization: Bearer CURSOR_API_KEY` instead of **cursor-agent** (no Cursor desktop app required). Base URL only, e.g. `https://your-bridge.example/v1`. |
| `CODE_AGENTS_HTTP_ONLY` | — | If `1`/`true`/`yes`, never spawn **cursor-agent**; **`CURSOR_API_URL` is required** or requests fail fast with a clear error (use when debugging headless setups). |
| `ANTHROPIC_API_KEY` | — | API key for claude backend |
| `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` | — | Optional. Path to a PEM CA bundle so HTTPS to third parties (e.g. **Atlassian** `auth.atlassian.com` during OAuth) verifies correctly behind TLS inspection. |
| `CODE_AGENTS_HTTPS_VERIFY` / `ATLASSIAN_OAUTH_HTTPS_VERIFY` | — | If `0` / `false` / `no` / `off`, disables TLS verification for **Atlassian OAuth token** HTTP calls only (**insecure**; local troubleshooting). Prefer `SSL_CERT_FILE`. |
| `OPEN_WEBUI_PUBLIC_URL` / `OPEN_WEBUI_URL` | — | Optional. Origin where Open WebUI runs (e.g. `http://localhost:8080`). After **`/oauth/atlassian`** succeeds, HTML links point here; chat stays separate from the Code Agents port. Helps avoid confusion (and Cursor stability issues) when mixing Open WebUI + Atlassian OAuth. |
| `ATLASSIAN_OAUTH_SUCCESS_REDIRECT` | — | Optional. If set, after a **successful** Atlassian login the server sends **302** to this URL (e.g. `http://localhost:8080/`) instead of an HTML success page. **`start-with-open-webui.sh`** defaults it to `OPEN_WEBUI_PUBLIC_URL`. |

## Without the Cursor desktop app

The Cursor backend normally uses the **cursor-agent** CLI, which often expects the **Cursor desktop app** (local proxy). To avoid both:

1. Set **`CURSOR_API_URL`** in `.env` to an **OpenAI-compatible** base URL that accepts `Bearer` auth and `POST …/chat/completions` (your own bridge or provider — Cursor does not ship a public drop-in URL for this).
2. Keep **`CURSOR_API_KEY`** set as today. Restart Code Agents.

Or use the **Claude backend** (below) with only `ANTHROPIC_API_KEY`.

1. Install the Claude backend: `poetry install --with claude`
2. Set your key: `export ANTHROPIC_API_KEY=sk-ant-...` (or add to `.env`)
3. Enable the example agent: `mv agents/claude_example.yaml.disabled agents/claude_example.yaml`
4. Restart Code Agents. In Open WebUI (URL: `http://localhost:8000/v1`) you’ll see **claude-coder** as a model — use it for chat. No Cursor app required.

You can keep your existing Cursor-based agents; they will work when the Cursor app is running. Use Claude-based agents when you want to run fully headless.

## Troubleshooting

- **`cursor-agent failed with exit code 1` when prompting**  
  Usually the CLI cannot reach Cursor (local proxy / desktop app). Options: run the **Cursor desktop app**, set **`CURSOR_API_URL`** for the HTTP path (see env table), or use the **Claude backend**.  
  Check setup without secrets: `GET http://localhost:8000/diagnostics` (shows whether `CURSOR_API_URL` / key are set, **`package_version`**, **`backend_py`**, and which backends each agent uses). If a traceback mentions **`agent_debug_request_middleware`**, you are on an **old** server build — restart after `git pull`.

- **`Cannot use this model: code-reasoning` (or another agent id) in cursor-agent stderr**  
  The request `model` is only for **routing**; the CLI uses YAML **`model`**. Use a value your `cursor-agent` accepts (e.g. `composer-1.5`). Current server builds do not pass the OpenAI model string through as the backend model id.

- **`Authentication required… set CURSOR_API_KEY`** (stderr) with keys only in **`.env`**  
  Agent YAML expands `${CURSOR_API_KEY}` when agents load. The app now runs **`load_dotenv()` before loading agents** on startup, so **`uvicorn code_agents.app:app`** behaves like **`python -m code_agents`**. Restart after changing `.env`.

- **`Security command failed` / security process exit `161`** (macOS)  
  The CLI got past API-key checks but Cursor’s security helper failed. Run the **Cursor desktop app**, or use **`CURSOR_API_URL`** / a **Claude** agent for a fully headless setup.

- **Open WebUI shows "Attempt to decode JSON with unexpected mimetype: text/plain"**  
  The server returns errors as JSON. Restart the Code Agents server so the change is active.

- **`422` / validation error on `/v1/chat/completions`**  
  Some clients send `"stream": "true"` as a **string**. Request bodies are normalized so string booleans are accepted; restart the server after upgrading.

- **`422` on `messages[].content`**  
  Some UIs send **multimodal** `content` as a **list** of `{type, text}` parts. Those are flattened to a single string (non-text parts are skipped).

- **Streaming (`stream: true`) returns HTTP 200 even when the agent fails**  
  SSE commits response headers before the stream body runs, so **cursor-agent** failures usually appear as an error line in the SSE payload (or in server logs), not as HTTP 502. For a JSON **502** with `process_error`, use **non-streaming** requests or fix **CURSOR_API_URL** / desktop / Claude per the main troubleshooting bullets.

- **`agent-router` (or another YAML agent) never runs in Open WebUI; only some agents work**  
  If the OpenAI connection **API base URL** is **`http://localhost:8000/v1/agents/some-agent`** (one agent per connection), that connection **only** talks to `some-agent`. **`agent-router` needs its own URL** — **`http://localhost:8000/v1/agents/agent-router`** — or use a **single** connection to **`http://localhost:8000/v1`** and pick **`agent-router`** in the model list. See `GET http://localhost:8000/diagnostics` field **`open_webui_hint`**.

- **`ERROR: Exception in ASGI application` after `502` on `/v1/chat/completions`**  
  Usually fixed by avoiding `BaseHTTPMiddleware` around failing routes; this project logs debug events from the completions router instead. Restart the server after upgrading.

- **Atlassian OAuth: `CERTIFICATE_VERIFY_FAILED` / `unable to get local issuer certificate` on `/oauth/atlassian/callback`**  
  Python cannot verify TLS to **`auth.atlassian.com`** (often seen with **corporate SSL inspection** or a custom trust store). Prefer **`SSL_CERT_FILE=/path/to/bundle.pem`** (or **`REQUESTS_CA_BUNDLE`**) that includes your org’s root CA. As a last resort for local dev: **`CODE_AGENTS_HTTPS_VERIFY=0`** (or **`ATLASSIAN_OAUTH_HTTPS_VERIFY=0`**). See **`examples/README-atlassian-mcp.md`** for the full env table.
  The HTTP status for this case is **503** (connection/TLS to Atlassian), not “wrong **redirect_uri**” — **`502`** is reserved for **5xx** responses from Atlassian’s token endpoint after a successful TLS handshake.

- **Cursor crashes when Atlassian OAuth finishes (with Open WebUI)**  
  Run **`/oauth/atlassian/`** in **Safari, Chrome, or Firefox** — not Cursor’s embedded browser. Set **`OPEN_WEBUI_PUBLIC_URL=http://localhost:8080`** for clearer post-login links. Avoid running **Cursor’s own Atlassian MCP** OAuth at the same moment as this flow.

## Project Structure

```
code-agents/
  pyproject.toml              # Poetry project config
  poetry.lock                 # Locked dependencies
  Dockerfile
  LICENSE
  agents/                     # YAML agent definitions
    agent_router.yaml         #   Triage entry point — recommends specialist agents
    code_reasoning.yaml       #   Read-only code analysis agent
    code_writer.yaml          #   Code generation agent
    code_reviewer.yaml        #   Code review agent
    code_tester.yaml          #   Testing, debugging, and code quality agent
    redash_query.yaml         #   Database query agent via Redash
    claude_example.yaml.disabled  # Claude backend example
  code_agents/                # Python package
    main.py                   #   Entry point (uvicorn)
    app.py                    #   FastAPI app, CORS, lifespan
    config.py                 #   Settings + AgentLoader
    models.py                 #   Pydantic request/response models
    backend.py                #   Backend abstraction (cursor/claude)
    stream.py                 #   SSE streaming + response builders
    routers/
      completions.py          #   POST /v1/agents/{name}/chat/completions
      agents_list.py          #   GET /v1/agents, GET /v1/models
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b my-feature`
3. Install dev dependencies: `poetry install --with dev`
4. Make your changes
5. Run tests: `poetry run pytest`
6. Submit a pull request

## License

[MIT](LICENSE)
