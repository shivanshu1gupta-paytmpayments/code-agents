# Architecture — Code Agents

## Overview

Code Agents is a CLI-first AI agent platform. Users define agents in YAML, interact via terminal chat, and automate CI/CD pipelines. The system exposes all agents as OpenAI-compatible API endpoints.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                              │
│                                                                     │
│  code-agents chat          Terminal REPL (chat.py)                  │
│  code-agents start         FastAPI Server (app.py)                  │
│  Open WebUI / curl         HTTP API (routers/)                      │
└──────────────┬──────────────────────────┬───────────────────────────┘
               │                          │
               ▼                          ▼
┌──────────────────────┐    ┌─────────────────────────────────────────┐
│    Chat REPL          │    │           FastAPI Server                │
│                       │    │                                         │
│  Agent picker menu    │    │  POST /v1/agents/{name}/chat/completions│
│  Slash commands       │    │  GET  /v1/agents                        │
│  Inline delegation    │    │  GET  /health, /diagnostics             │
│  Command execution    │    │                                         │
│  Agentic loop         │    │  Routers:                               │
│  Tab-completion       │    │    completions → stream.py → backend.py │
│  Ctrl+O collapse      │    │    jenkins, argocd, git_ops, testing    │
│  Session persistence  │    │    pipeline, redash, elasticsearch      │
└──────────┬────────────┘    └──────────────┬──────────────────────────┘
           │                                │
           ▼                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        BACKEND LAYER                                │
│                                                                     │
│  backend.py — dispatches to one of 3 backends:                      │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐                │
│  │   Cursor     │  │  Claude API  │  │  Claude CLI   │               │
│  │  (SDK/CLI)   │  │  (SDK)       │  │  (subscription)│              │
│  │             │  │              │  │               │               │
│  │ cursor-agent│  │ claude-agent │  │ claude --print│               │
│  │ --print     │  │ -sdk         │  │ --output json │               │
│  │ --trust     │  │              │  │ --model ...   │               │
│  └─────────────┘  └─────────────┘  └──────────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Request Flow

### Chat REPL Path (code-agents chat)

```
User types message
    │
    ▼
chat.py:chat_main()
    │
    ├── Load rules (rules_loader.py — fresh from disk every message)
    ├── Build system context (_build_system_context)
    │     ├── Repo path + project name
    │     ├── Bash tool instructions
    │     └── Agent rules (global + project)
    │
    ├── POST /v1/agents/{agent}/chat/completions
    │     │
    │     ▼
    │   routers/completions.py → stream.py
    │     │
    │     ├── Inject rules into agent.system_prompt
    │     ├── build_prompt() — pack conversation history
    │     └── backend.py:run_agent()
    │           │
    │           ├── cursor backend → cursor-agent CLI
    │           ├── claude backend → claude-agent-sdk
    │           └── claude-cli backend → claude --print
    │
    ├── Stream response (show spinner + timer)
    │
    ├── Auto-collapse if >25 lines (Ctrl+O to toggle)
    │
    ├── Extract ```bash commands from response
    │     │
    │     ├── Check if command is trusted (saved in rules)
    │     │     ├── Yes → auto-run
    │     │     └── No → prompt: 1. Yes / 2. Yes & Save / 3. No
    │     │
    │     ├── Resolve {placeholders} and <PLACEHOLDERS>
    │     ├── Run command (with live timer + Jenkins polling after 120s)
    │     └── Feed output back to agent (agentic loop)
    │
    └── Save session to chat_history/
```

### API Path (curl / Open WebUI)

```
HTTP POST /v1/agents/{agent}/chat/completions
    │
    ▼
routers/completions.py
    │
    ├── Resolve agent by name/display_name/model
    ├── stream_response() or collect_response()
    │     │
    │     ▼
    │   stream.py
    │     ├── load_rules(agent, cwd) — inject into system_prompt
    │     ├── build_prompt(messages) — single or multi-turn
    │     └── run_agent(agent, prompt)
    │           │
    │           ▼
    │         backend.py → cursor/claude/claude-cli
    │
    └── Return SSE stream or JSON response
```

---

## Module Map

### Core

| Module | Purpose |
|--------|---------|
| `cli.py` | 23 CLI commands. Entry point: `code-agents <command>` |
| `chat.py` | Interactive REPL. Slash commands, agent switching, command execution, agentic loop, session persistence |
| `app.py` | FastAPI server. CORS, lifespan, request/response logging middleware |
| `main.py` | Uvicorn launcher. Loads env, starts server |
| `config.py` | `AgentConfig` dataclass, `Settings`, `AgentLoader` (reads YAML, expands `${VAR}`) |
| `backend.py` | Backend dispatcher: cursor CLI, cursor HTTP, claude SDK, claude CLI |
| `stream.py` | SSE streaming. Converts SDK messages to OpenAI-compatible chunks. `build_prompt()` for multi-turn |
| `models.py` | Pydantic request/response models (OpenAI-compatible) |

### Configuration & Rules

| Module | Purpose |
|--------|---------|
| `env_loader.py` | Two-tier config: `~/.code-agents/config.env` (global) + `.env.code-agents` (per-repo) |
| `rules_loader.py` | Two-tier rules: `~/.code-agents/rules/` (global) + `.code-agents/rules/` (project). Auto-refresh on every message |
| `chat_history.py` | Session persistence: auto-save to `~/.code-agents/chat_history/`, resume, list, delete |
| `setup.py` | Interactive setup wizard (7 steps). `prompt()` with validation + transform |

### CI/CD Clients

| Module | Purpose |
|--------|---------|
| `jenkins_client.py` | Jenkins REST API: trigger, poll, logs, job discovery, parameter introspection, build version extraction |
| `argocd_client.py` | ArgoCD REST API: status, pods, logs, sync, rollback |
| `git_client.py` | Async git subprocess wrapper: branches, diff, log, status, push |
| `testing_client.py` | Test runner + coverage XML parser. Auto-detects pytest/jest/maven/gradle/go |
| `pipeline_state.py` | 6-step pipeline state machine: connect → review → build → deploy → verify → rollback |

### API Routers

| Router | Endpoints |
|--------|-----------|
| `completions.py` | `POST /v1/agents/{name}/chat/completions` |
| `agents_list.py` | `GET /v1/agents`, `GET /v1/models` |
| `jenkins.py` | `/jenkins/jobs`, `/jenkins/jobs/{path}/parameters`, `/jenkins/build`, `/jenkins/build-and-wait` |
| `argocd.py` | `/argocd/apps/{name}/status`, `/pods`, `/logs`, `/sync`, `/rollback` |
| `git_ops.py` | `/git/branches`, `/git/diff`, `/git/log`, `/git/status`, `/git/push` |
| `testing.py` | `/testing/run`, `/testing/coverage`, `/testing/gaps` |
| `pipeline.py` | `/pipeline/start`, `/pipeline/{id}/status`, `/pipeline/{id}/advance` |
| `redash.py` | `/redash/data-sources`, `/redash/run-query`, `/redash/run-saved-query` |
| `elasticsearch.py` | `/elasticsearch/info`, `/elasticsearch/search` |

### Other

| Module | Purpose |
|--------|---------|
| `message_types.py` | Dataclasses shared with cursor/claude SDKs: `AssistantMessage`, `TextBlock`, `ToolUseBlock` |
| `logging_config.py` | Hourly rotating file handler (168 backups = 7 days) |
| `openai_errors.py` | OpenAI-compatible error response formatting |
| `public_urls.py` | URL helpers for OAuth callbacks |
| `redash_client.py` | Redash API client: data sources, schemas, query execution |
| `elasticsearch_client.py` | Elasticsearch client: search, info |
| `atlassian_oauth.py` | Atlassian OAuth 2.0 token exchange |

---

## Data Flow: Backends

### Cursor Backend (default)

```
backend.py
  → cursor_agent_sdk.query(prompt, options)
    → spawns cursor-agent --print --trust --model "composer 1.5"
      → cursor-agent talks to Cursor's LLM API
        → returns stream-json messages
```

Requires: `CURSOR_API_KEY` + `cursor-agent` CLI installed.

### Claude API Backend

```
backend.py
  → claude_agent_sdk.query(prompt, options)
    → calls Anthropic Messages API
      → returns stream messages
```

Requires: `ANTHROPIC_API_KEY`.

### Claude CLI Backend (subscription — no API key)

```
backend.py
  → subprocess: claude --print --output-format json --model claude-sonnet-4-6
    → uses Claude Pro/Max subscription auth
      → returns JSON result
```

Requires: `claude` CLI installed + logged in. No API key needed.
Enable: `CODE_AGENTS_BACKEND=claude-cli`

---

## Data Flow: Configuration

```
~/.code-agents/
  ├── config.env              Global config (API keys, server, integrations)
  ├── rules/                  Global rules
  │   ├── _global.md          → all agents, all projects
  │   └── code-writer.md      → code-writer agent only
  └── chat_history/           Saved chat sessions
      └── {uuid}.json

{repo}/
  ├── .env.code-agents        Per-repo config (Jenkins, ArgoCD, testing)
  └── .code-agents/
      └── rules/              Project rules
          ├── _global.md      → all agents in this repo
          ├── jenkins-build.md → jenkins-build agent only
          └── code-writer.md  → code-writer in this repo
```

Load order (later overrides earlier):
1. `~/.code-agents/config.env` (global, `override=False`)
2. `{cwd}/.env` (legacy fallback, `override=True`)
3. `{cwd}/.env.code-agents` (per-repo, `override=True`)

Rules merge order:
1. Global `_global.md`
2. Global `{agent-name}.md`
3. Project `_global.md`
4. Project `{agent-name}.md`

---

## Data Flow: Chat REPL

```
┌─────────────────────────────────────────────────┐
│                Chat Session                      │
│                                                  │
│  State:                                          │
│    agent: "jenkins-build"                        │
│    session_id: "5b38707a-..."                    │
│    repo_path: "/Users/.../pg-acquiring-biz"      │
│    _last_output: "..."                           │
│    _chat_session: {id, messages, ...}            │
│                                                  │
│  Input processing:                               │
│    /command     → _handle_command()              │
│    /<agent> msg → inline delegation              │
│    text         → send to current agent          │
│                                                  │
│  Output processing:                              │
│    Streaming    → _render_markdown()             │
│    > 25 lines   → auto-collapse + Ctrl+O toggle │
│    ```bash      → command detection + execution  │
│    Execution    → agentic feedback loop          │
│                                                  │
│  Slash commands:                                 │
│    /help /quit /agent /agents /rules /run /exec  │
│    /open /restart /session /clear /history       │
│    /resume /delete-chat /<agent> <prompt>         │
└─────────────────────────────────────────────────┘
```

---

## Agent YAML Schema

```yaml
name: jenkins-build                    # kebab-case, used in URLs
display_name: "Jenkins Build Agent"    # UI name
backend: cursor                        # cursor | claude | claude-cli
model: "composer 1.5"                  # backend model ID
system_prompt: |                       # multi-line, supports ${ENV_VAR}
  You are a Jenkins CI/CD agent...
permission_mode: default               # default | acceptEdits | bypassPermissions
api_key: ${CURSOR_API_KEY}             # env var expansion
cwd: "."                               # working directory
stream_tool_activity: true             # show tool calls in stream
include_session: true                  # return session_id
extra_args:                            # backend-specific flags
  mode: ask
```

---

## 14 Agents

| Agent | Role | Backend | Permission |
|-------|------|---------|------------|
| `auto-pilot` | Autonomous orchestrator — delegates to sub-agents | cursor | default |
| `agent-router` | Route to specialist | cursor | default |
| `code-reasoning` | Read-only analysis | cursor | bypassPermissions |
| `code-writer` | Write/modify code | cursor | acceptEdits |
| `code-reviewer` | Review for bugs | cursor | default |
| `code-tester` | Write tests, debug | cursor | acceptEdits |
| `qa-regression` | Full regression testing | cursor | acceptEdits |
| `redash-query` | SQL via Redash | cursor | default |
| `git-ops` | Git operations | cursor | default |
| `test-coverage` | Run tests, coverage | cursor | acceptEdits |
| `jenkins-build` | Trigger CI builds | cursor | default |
| `jenkins-deploy` | Trigger deployments | cursor | default |
| `argocd-verify` | Verify deployments | cursor | default |
| `pipeline-orchestrator` | End-to-end CI/CD | cursor | default |

---

## 6-Step CI/CD Pipeline

```
1. Connect     → git branches, diff, status
2. Review/Test → code-reviewer + test-coverage
3. Push/Build  → git push + jenkins-build (build-and-wait)
4. Deploy      → jenkins-deploy with build_version
5. Verify      → argocd-verify (pods, logs, health)
6. Rollback    → argocd rollback to previous revision
```

State machine: `pipeline_state.py`
API: `/pipeline/start`, `/pipeline/{id}/status`, `/pipeline/{id}/advance`, `/pipeline/{id}/rollback`

---

## Test Structure (230 tests)

| File | Tests | Coverage |
|------|-------|----------|
| `test_chat.py` | 83 | Chat REPL, slash commands, delegation, tab-completion, command extraction, placeholders, welcome messages |
| `test_chat_history.py` | 29 | Session CRUD, persistence, build_prompt |
| `test_cli.py` | 24 | All 23 commands in help, config, doctor, dispatcher |
| `test_env_loader.py` | 21 | Variable classification, load order, .env directory handling |
| `test_jenkins_client.py` | 20 | Job path encoding, build version extraction |
| `test_rules_loader.py` | 18 | Rules merge order, agent targeting, auto-refresh |
| `test_routers.py` | 14 | All FastAPI routers, pipeline lifecycle |
| `test_testing_client.py` | 18 | Test detection, coverage XML, pipeline state |
| `test_git_client.py` | 10 | Ref validation, branches, diff, log, status |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.10+ |
| Web framework | FastAPI + Uvicorn |
| Data models | Pydantic v2 |
| Agent config | YAML (`pyyaml`) |
| HTTP client | httpx (async) |
| LLM backends | cursor-agent-sdk, claude-agent-sdk, claude CLI |
| CI/CD | Jenkins REST API, ArgoCD REST API |
| Database queries | Redash API |
| Search | Elasticsearch client |
| Auth | Atlassian OAuth 2.0 |
| Testing | pytest + pytest-asyncio |
| Package manager | Poetry |
| Build | Makefile (40+ targets) |
