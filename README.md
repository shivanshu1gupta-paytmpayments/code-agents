# Code Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests: 201 passing](https://img.shields.io/badge/tests-201%20passing-brightgreen.svg)]()

AI-powered code agent platform with interactive chat and a built-in CI/CD pipeline. Define agents in YAML, chat with them from the terminal, and automate: **review → test → build → deploy → verify → rollback**.

## Install

```bash
# One-command install
curl -fsSL https://raw.githubusercontent.com/shivanshu1gupta-paytmpayments/code-agents/main/install.sh | bash

# Initialize in your project
cd /path/to/your-project
code-agents init          # configure keys, write config
code-agents start         # start the server (background)
code-agents chat          # interactive chat — pick an agent, start talking
```

## Interactive Chat

`code-agents chat` is the primary way to interact. Pick an agent from the menu, then talk:

```
$ code-agents chat

  Select an agent:

    1.    agent-router             Help pick the right specialist agent
    2.    code-reasoning           Analyze code, explain architecture, trace flows
    3.    code-reviewer            Review code for bugs, security issues, style
    4.    code-tester              Write tests, debug issues, optimize code quality
    5.    code-writer              Generate and modify code, refactor, implement
    6.    git-ops                  Git operations: branches, diffs, logs, push
    ...

  Pick agent [1-12]: 2

  you › Explain the architecture of this project
  code-reasoning › This project follows a layered architecture...

  you › /agent code-tester
  ✓ Switched to: code-tester

  you › Write unit tests for the auth module
  code-tester › I'll create tests for the auth module...

  you › /code-reviewer Review the auth module for security issues
  Delegating to code-reviewer: Review code for bugs, security issues, style violations
  code-reviewer › Looking at the auth module...
  (back to code-tester)
```

**Key features:**
- **Works on YOUR project** — auto-detects git repo from your current directory and passes it to the agent
- **Auto-starts server** — if server isn't running, offers to start it for you
- **Multi-turn sessions** — context is preserved across messages
- **Chat history persistence** — sessions auto-saved and can be resumed later
- **Session resume** — pick up any previous conversation right where you left off
- **Streaming** — responses appear in real-time as the agent types
- **Agent switching** — `/agent code-writer` switches permanently
- **Inline delegation** — `/<agent> <prompt>` sends a one-shot to another agent, then returns to your current agent
- **Tab-completion** — press Tab after `/` to autocomplete slash commands and agent names
- **Command execution** — agent suggests a shell command? Press `y` to run it right from chat, with JSON pretty-printing and agentic feedback loop
- **`/exec`** — run any command and auto-feed output to agent for analysis
- **Agent rules** — persistent instructions per-agent or global, auto-refresh mid-chat

Chat commands: `/help /quit /agents /agent <name> /rules /run <cmd> /exec <cmd> /restart /session /clear /history /resume <id> /delete-chat <id> /<agent> <prompt>`

## CLI Commands

```
code-agents help                         # full help with all args
```

### Getting Started
| Command | Args | Description |
|---------|------|-------------|
| `init` | | Configure keys, write global + per-repo config |
| `migrate` | | Migrate legacy .env to centralized config |
| `start` | `[--fg]` | Start server (background). `--fg` for foreground |
| `restart` | | Restart the server (shutdown + start) |
| `chat` | `[agent-name] [--resume <id>]` | Interactive chat. No args = show agent picker. `--resume` to continue a saved session |
| `setup` | | Full interactive setup wizard (7 steps) |
| `completions` | `[--install\|--zsh\|--bash]` | Install shell tab-completion |

### Server Management
| Command | Args | Description |
|---------|------|-------------|
| `shutdown` | | Stop the running server (kills process on port) |
| `status` | | Server health, version, integrations, curl commands |
| `logs` | `[lines]` | Tail log file live. Default: 50 lines |
| `config` | | Show .env config (secrets masked) |
| `doctor` | | Diagnose issues (Python, keys, SDK, server, Jenkins, ArgoCD) |

### Git Operations
| Command | Args | Description |
|---------|------|-------------|
| `branches` | | List branches, highlight current |
| `diff` | `[base] [head]` | Diff between branches. Default: `main HEAD` |

### CI/CD & Testing
| Command | Args | Description |
|---------|------|-------------|
| `test` | `[branch]` | Run tests. Auto-detects pytest/jest/maven/gradle/go |
| `review` | `[base] [head]` | AI code review via code-reviewer agent |
| `pipeline start` | `[branch]` | Start 6-step CI/CD pipeline |
| `pipeline status` | `[run_id]` | Show pipeline status. No arg = list all |
| `pipeline advance` | `<run_id>` | Advance to next step |
| `pipeline rollback` | `<run_id>` | Trigger rollback |

### Information
| Command | Args | Description |
|---------|------|-------------|
| `agents` | | List all 13 agents |
| `curls` | `[category\|agent]` | Show API curl commands. Filter by category or agent |
| `version` | | Version, Python, install path |
| `sessions` | `[--all \| delete <id> \| clear]` | List/manage saved chat sessions |
| `help` | | Full help with all args and examples |
| `rules` | `[list\|create\|edit\|delete]` | Manage agent rules (see below) |
| `migrate` | | Migrate legacy .env to centralized config |

## Agent Rules

Persistent instructions that get injected into agent system prompts. Rules auto-refresh — edit a file mid-chat and the next message picks it up.

### Two tiers

| Tier | Location | Scope |
|------|----------|-------|
| Global | `~/.code-agents/rules/` | All projects |
| Project | `{repo}/.code-agents/rules/` | This project only |

### Targeting

| File name | Applies to |
|-----------|-----------|
| `_global.md` | All agents |
| `code-writer.md` | Only the `code-writer` agent |
| `code-reviewer.md` | Only the `code-reviewer` agent |

### Usage

```bash
# Create rules
code-agents rules create                      # project rule → all agents
code-agents rules create --agent code-writer  # project rule → code-writer only
code-agents rules create --global             # global rule → all agents, all projects

# List active rules
code-agents rules                             # list all
code-agents rules list --agent code-writer    # list for specific agent

# Edit / delete
code-agents rules edit <path>                 # open in $EDITOR
code-agents rules delete <path>               # delete with confirmation
```

In chat: `/rules` shows active rules for the current agent.

### Example

```
~/.code-agents/rules/_global.md:
  Always respond in English. Be concise.

myrepo/.code-agents/rules/code-writer.md:
  This is a Django 4.2 project using PostgreSQL 14.
  Use 4-space indentation. Follow PEP 8.
  Always add type hints to new functions.
```

## Agents (13)

| Agent | Role | Permissions |
|---|---|---|
| `agent-router` | Recommends which specialist to use | Read-only |
| `code-reasoning` | Explains architecture, traces flows, analyzes code | Read-only |
| `code-writer` | Writes/modifies code, refactors, implements features | Auto-approve edits |
| `code-reviewer` | Reviews for bugs, security issues, style violations | Read-only |
| `code-tester` | Writes tests, debugs, optimizes code quality | Auto-approve edits |
| `redash-query` | SQL queries, schema exploration via Redash | Read-only |
| `git-ops` | Git branches, diffs, logs, push | Read-only |
| `test-coverage` | Runs test suites, coverage reports, finds gaps | Auto-approve edits |
| `jenkins-build` | Triggers/monitors Jenkins CI builds | Read-only |
| `jenkins-deploy` | Triggers/monitors Jenkins deployments | Read-only |
| `argocd-verify` | Checks ArgoCD pods, scans logs, rollbacks | Read-only |
| `qa-regression` | Runs regression suites, writes missing tests, eliminates manual QA | Auto-approve edits |
| `pipeline-orchestrator` | Guides full CI/CD pipeline end-to-end | Read-only |

## CI/CD Pipeline

6-step deployment pipeline:

```
1. Connect      → Verify repo, show branch diff
2. Review/Test  → AI code review + run tests + verify coverage
3. Push/Build   → Push code, trigger Jenkins build
4. Deploy       → Trigger Jenkins deployment job
5. Verify       → Check ArgoCD pods, scan logs for errors
6. Rollback     → Revert to previous revision (if anything fails)
```

REST APIs: `/pipeline/*`, `/git/*`, `/testing/*`, `/jenkins/*`, `/argocd/*`

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CURSOR_API_KEY` | Cursor backend API key |
| `ANTHROPIC_API_KEY` | Claude backend API key |
| `CODE_AGENTS_BACKEND` | Set to `claude-cli` to use Claude subscription (no API key) |
| `CODE_AGENTS_CLAUDE_CLI_MODEL` | Model for claude-cli (default: `claude-sonnet-4-6`) |
| `HOST` / `PORT` | Server bind (default `0.0.0.0:8000`) |
| `TARGET_REPO_PATH` | Target repo (auto-detected from cwd) |
| `JENKINS_URL` | Jenkins server URL |
| `JENKINS_USERNAME` / `JENKINS_API_TOKEN` | Jenkins auth |
| `JENKINS_BUILD_JOB` / `JENKINS_DEPLOY_JOB` | Job paths (not URLs) |
| `ARGOCD_URL` / `ARGOCD_AUTH_TOKEN` / `ARGOCD_APP_NAME` | ArgoCD config |

Full list: `.env.example`

## Logging

- File: `logs/code-agents.log` (current hour only)
- Hourly rotation → `code-agents.log.2026-03-22_14`
- 7 days retention (168 hourly backups)
- `code-agents logs` to tail live

## Testing

```bash
poetry run pytest       # 201 tests
code-agents doctor      # diagnose setup
code-agents test        # run tests on target repo
```

## Open WebUI Integration

1. `code-agents start`
2. Open WebUI → Settings → Connections → OpenAI
3. URL: `http://localhost:8000/v1`, Key: any string
4. All 13 agents appear as models

## Docker

```bash
docker build -t code-agents .
docker run -p 8000:8000 -e CURSOR_API_KEY=your-key code-agents
```

## Project Structure

```
code-agents/
  install.sh                    # One-command installer
  pyproject.toml                # Poetry config, CLI entry points
  agents/                       # 12 YAML agent definitions
    agent_router.yaml           code_reasoning.yaml
    code_writer.yaml            code_reviewer.yaml
    code_tester.yaml            redash_query.yaml
    git_ops.yaml                test_coverage.yaml
    jenkins_build.yaml          jenkins_deploy.yaml
    argocd_verify.yaml          pipeline_orchestrator.yaml
  code_agents/                  # Python package
    cli.py                      #   CLI: 22 commands (init/migrate/start/chat/shutdown/...)
    chat.py                     #   Interactive chat REPL with streaming + tab-completion
    setup.py                    #   Interactive setup wizard
    main.py                     #   Uvicorn server entry point
    app.py                      #   FastAPI app, middleware, logging
    config.py                   #   Settings + AgentLoader
    env_loader.py               #   Centralized env loading (global + per-repo)
    rules_loader.py             #   Agent rules (global + project, auto-refresh)
    backend.py                  #   Backend abstraction (cursor/claude, claude-agent-sdk built-in)
    chat_history.py             #   Chat session persistence (auto-save, resume, UUID-based)
    stream.py                   #   SSE streaming + response builders + build_prompt()
    models.py                   #   Pydantic request/response models
    logging_config.py           #   Hourly rotating file + console logging
    git_client.py               #   Async git operations
    testing_client.py           #   Test runner + coverage parser
    jenkins_client.py           #   Jenkins REST API client
    argocd_client.py            #   ArgoCD REST API client
    pipeline_state.py           #   Pipeline state machine
    redash_client.py            #   Redash query client
    elasticsearch_client.py     #   Elasticsearch client
    atlassian_oauth.py          #   Atlassian OAuth 2.0
    routers/                    #   FastAPI route handlers
      completions.py  agents_list.py  git_ops.py  testing.py
      jenkins.py  argocd.py  pipeline.py  redash.py
      elasticsearch.py  atlassian_oauth_web.py
  tests/                        # 230 tests
    test_chat.py                #   Chat REPL, slash commands, agent parsing, SSE, delegation, tab-completion
    test_cli.py                 #   CLI commands, help, config, curls, dispatcher
    test_git_client.py          #   Git operations (real temp repos)
    test_jenkins_client.py      #   Jenkins + ArgoCD client init
    test_routers.py             #   All FastAPI routers + pipeline lifecycle
    test_env_loader.py          #   Centralized config loading, var classification
    test_rules_loader.py        #   Rules loading, merge order, agent targeting
    test_testing_client.py      #   Test detection, coverage, pipeline state
    test_chat_history.py       #   Session CRUD, persistence, build_prompt
  scripts/                      # Utility scripts
  initiater/                    # Project audit system (14 rules)
  logs/                         # Hourly-rotated log files
```

## Contributing

1. Fork → `git checkout -b my-feature`
2. `poetry install --with dev`
3. Make changes → `poetry run pytest`
4. Submit PR

## License

[MIT](LICENSE) — Copyright (c) 2026 Paytm Payments Services Limited (Regulated by RBI)