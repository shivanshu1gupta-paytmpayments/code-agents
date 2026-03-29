# Release Notes — Code Agents

## v0.2.0 — 2026-03-25

### Highlights

**Auto-Pilot Agent** — A fully autonomous orchestrator that delegates to sub-agents (code-writer, jenkins-cicd, argocd-verify) and runs complete workflows without manual intervention.

**Claude CLI Backend** — Use your Claude Pro/Max subscription directly. No API key needed. Set `CODE_AGENTS_BACKEND=claude-cli` and go.

**Agent Rules System** — Two-tier rules (global + per-project) that inject context into agent system prompts. Auto-refresh on every message. Manage via `code-agents rules` CLI or `/rules` in chat.

**Interactive Chat Overhaul** — Claude Code-style REPL with spinner + timer, vertical Tab selector for command approval, Ctrl+O collapse/expand for long responses, auto-collapse after 25 lines, session persistence with `/resume`.

**Token Tracking** — Per message/session/day/month/year tracking with CSV export. `/tokens` command shows usage breakdown by backend and model.

### New Agents
- **auto-pilot** — Autonomous orchestrator, delegates to sub-agents
- **jenkins-cicd** — Merged build + deploy into single agent (replaces jenkins-build + jenkins-deploy)
- **qa-regression** — Full regression testing, eliminates manual QA

### New CLI Commands
- `code-agents rules` — Manage agent rules (list/create/edit/delete)
- `code-agents sessions` — List saved chat sessions
- `code-agents update` — Pull latest + reinstall dependencies
- `code-agents restart` — Restart server (shutdown + start)
- `code-agents completions --install` — Shell tab-completion for zsh/bash

### New Chat Features
- Inline agent delegation: `/<agent> <prompt>` for one-shot delegation
- Tab-completion for slash commands and agent names
- `/tokens` — Token usage breakdown (session, daily, monthly, yearly)
- `/exec <cmd>` — Run command and feed output to agent
- `/history` + `/resume` — Session persistence
- Agent welcome messages in red bordered box with capabilities + examples
- Auto-fill `BUILD_VERSION` from previous build output
- Trusted command auto-approval (save to rules)

### Backend Improvements
- 3 backends: cursor-agent-sdk, claude-agent-sdk, claude CLI (subscription)
- Centralized .env config: global (`~/.code-agents/config.env`) + per-repo (`.env.code-agents`)
- Jenkins job discovery with parameter introspection
- Build-and-wait with automatic version extraction (7 regex patterns)
- Async connection validator for backend health checks

### Bug Fixes
- Terminal crash from raw mode corruption in Ctrl+O and Tab selector
- Build version extraction for Docker multi-stage builds
- Output box uses full terminal width (no 100-char cap)
- Stale jenkins-build/jenkins-deploy references removed
- Shallow copy mutation leaks in backend.py and stream.py
- Race condition in rules file read/write (now uses fcntl locking)
- Chat startup latency reduced (removed slow workspace trust check)

---

## v0.1.0 — 2026-03-20

### Highlights

**Initial Release** — 12 agents, FastAPI server, OpenAI-compatible API endpoints.

### Features
- Interactive chat REPL with streaming
- Jenkins CI/CD integration (build + deploy)
- ArgoCD deployment verification
- Git operations agent
- Redash SQL query agent
- Pipeline orchestrator (6-step CI/CD)
- Open WebUI integration
- Agent router for automatic delegation
