# Contributing to Code Agents

Copyright (c) 2026 Paytm Payments Services Limited (Regulated by RBI)

## Change Checklist

When making changes to the project, use this checklist to ensure everything stays in sync.
Not all items apply to every change — only update what's relevant.

### Adding a New Agent

- [ ] Create `agents/<name>.yaml`
- [ ] Add to `agents/agent_router.yaml` system prompt (specialists list)
- [ ] Add role to `AGENT_ROLES` dict in `code_agents/chat.py`
- [ ] Add example prompts to `_AGENT_EXAMPLES` dict in `code_agents/cli.py`
- [ ] Add to `Agents.md` with its own section
- [ ] Add to `README.md` agents table
- [ ] Add to `CLAUDE.md` architecture section
- [ ] Add to `cursor.md` architecture section
- [ ] Add tests if agent has special behavior
- [ ] Run: `poetry run python initiater/run_audit.py --rules workflow`

### Adding a New CLI Command

- [ ] Add function `cmd_<name>()` in `code_agents/cli.py`
- [ ] Add to `COMMANDS` dict in `cli.py`
- [ ] Add to `cmd_help()` — with full args, description, and examples
- [ ] Add to dispatcher in `main()` function
- [ ] Add tests in `tests/test_cli.py`
- [ ] Update `README.md` CLI commands table
- [ ] Update `CLAUDE.md` quick reference
- [ ] Update `cursor.md` quick reference

### Adding a New Chat Slash Command

- [ ] Add handler in `_handle_command()` in `code_agents/chat.py`
- [ ] Add to `/help` output inside `_handle_command()`
- [ ] Add to `cmd_help()` chat slash commands section in `cli.py`
- [ ] Add tests in `tests/test_chat.py` TestSlashCommands class
- [ ] Update `Agents.md` chat commands list

### Adding a New REST API / Router

- [ ] Create `code_agents/routers/<name>.py`
- [ ] Create client `code_agents/<name>_client.py` (if external API)
- [ ] Register router in `code_agents/app.py`
- [ ] Add curl examples to `_print_curl_sections()` in `cli.py`
- [ ] Add category to `cmd_curls()` categories list
- [ ] Add to `code-agents curls` help text
- [ ] Add tests in `tests/test_routers.py`
- [ ] Add env vars to `.env.example`
- [ ] Add to `code-agents doctor` checks in `cli.py`
- [ ] Update `README.md` — REST APIs section, env vars table
- [ ] Update `CLAUDE.md` architecture section
- [ ] Update `cursor.md` architecture section

### Adding a New Integration (Jenkins, ArgoCD, etc.)

- [ ] Create client module `code_agents/<name>_client.py`
- [ ] Create router `code_agents/routers/<name>.py`
- [ ] Create agent YAML `agents/<name>.yaml`
- [ ] Add env vars to `.env.example` and `.env` template in `setup.py`
- [ ] Add to `code-agents doctor` checks
- [ ] Add to `code-agents curls` sections
- [ ] Add to `code-agents init` prompts in `cli.py` or `setup.py`
- [ ] Follow "Adding a New Agent" checklist above
- [ ] Follow "Adding a New REST API" checklist above

### Changing Environment Variables

- [ ] Update `.env.example` with description
- [ ] Update `code_agents/setup.py` prompts (if user-facing)
- [ ] Update `code_agents/cli.py` `cmd_init()` prompts
- [ ] Update `code-agents doctor` checks
- [ ] Update `README.md` env vars table
- [ ] Update `CLAUDE.md` environment section
- [ ] Update `cursor.md` environment section

### Updating Tests

- [ ] Run: `poetry run pytest` — all tests must pass
- [ ] Update test count in: `README.md`, `CLAUDE.md`, `cursor.md`
- [ ] If new test file: add to `README.md` project structure

---

## Files That Reference Each Other

These files must stay in sync. When you change one, check the others:

| What changed | Files to update |
|-------------|----------------|
| Agent list | `agent_router.yaml`, `chat.py` (AGENT_ROLES), `cli.py` (_AGENT_EXAMPLES + help), `Agents.md`, `README.md`, `CLAUDE.md`, `cursor.md` |
| CLI commands | `cli.py` (function + COMMANDS + help + dispatcher), `README.md`, `CLAUDE.md`, `cursor.md` |
| Chat slash commands | `chat.py` (_handle_command + /help), `cli.py` (cmd_help chat section), `test_chat.py`, `Agents.md` |
| REST endpoints | `routers/*.py`, `cli.py` (curls), `README.md`, `CLAUDE.md`, `cursor.md` |
| Env variables | `.env.example`, `setup.py`, `cli.py` (init + doctor), `README.md`, `CLAUDE.md`, `cursor.md` |
| Test count | `README.md` (badge + text), `CLAUDE.md`, `cursor.md` |
| Copyright | `LICENSE`, `README.md` footer, `Agents.md` footer |
| Install URL | `install.sh`, `cli.py` (cmd_help), `README.md` |

---

## Dev Workflow

```bash
# Install dev dependencies
poetry install --with dev

# Run tests (must be 98+ passing)
poetry run pytest

# Check project quality
poetry run python initiater/run_audit.py

# Verify CLI works
code-agents help
code-agents doctor
code-agents agents

# Test a change interactively
code-agents start
code-agents chat
```

---

## Commit Message Format

```
<type>: <short description>

<body — what changed and why>

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`
