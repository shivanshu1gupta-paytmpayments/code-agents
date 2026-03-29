# Changelog

All notable changes to Code Agents are documented here.

## [Unreleased]

### Added
- Token tracking: per message/session/day/month/year with CSV export (`~/.code-agents/token_usage.csv`)
- `/tokens` command in chat — view usage breakdown by session, daily, monthly, yearly, backend/model
- Auto-fill `BUILD_VERSION` placeholder from previous build output
- Vertical Tab selector for command approval
- Safe Ctrl+O collapse/expand for long responses
- Session summary on exit with token counts and cost
- Async connection validator for backend health checks (cursor/claude/claude-cli)
- `gemini.md` — Gemini IDE context file
- `RELEASE-NOTES.md` — release notes for version tracking

### Fixed
- Terminal crash from raw mode corruption in Ctrl+O and Tab selector
- Build version extraction for Docker multi-stage builds
- Output box uses full terminal width (no 100-char cap)
- Stale jenkins-build/jenkins-deploy references removed

## [0.2.0] — 2026-03-25

### Added
- **Auto-Pilot agent** — autonomous orchestrator that delegates to sub-agents
- **Jenkins CI/CD agent** — merged build + deploy into single agent
- **QA Regression agent** — eliminate manual testing
- **Claude CLI backend** — use Claude subscription, no API key needed
- **Agent rules system** — global + project rules, auto-refresh mid-chat
- **Chat history persistence** — auto-save sessions, resume with `/resume`
- **Command execution engine** — detect ```bash blocks, run with approval
- **Agentic loop** — command output fed back to agent automatically
- **Shell tab-completion** — `code-agents` CLI + in-chat slash commands
- **Agent welcome messages** — red bordered box with capabilities + examples
- **Jenkins job discovery** — list jobs, fetch parameters, build-and-wait
- **Code-agents update** — pull latest + reinstall dependencies
- **Makefile** — 40+ targets for all operations
- 13 agents, 23 CLI commands, 247 tests

### Changed
- Centralized .env config: global (`~/.code-agents/config.env`) + per-repo (`.env.code-agents`)
- Rewritten core agent system prompts (senior engineer quality)
- Claude Code-style REPL: spinner, timer, markdown rendering, Tab selector
- Split god files: chat.py, cli.py, setup.py into focused modules

### Fixed
- 10 bugs found in code review (placeholder saving, Jenkins path stripping, race conditions, shallow copies)
- Workspace trust: auto-trust via `--trust` flag, removed slow pre-flight check
- Terminal crash: signal-safe raw mode with guaranteed restore

## [0.1.0] — 2026-03-20

### Added
- Initial release: 12 agents, FastAPI server, OpenAI-compatible API
- Interactive chat REPL with streaming
- Jenkins CI/CD integration (build + deploy)
- ArgoCD deployment verification
- Git operations agent
- Redash SQL query agent
- Pipeline orchestrator (6-step CI/CD)
- Open WebUI integration