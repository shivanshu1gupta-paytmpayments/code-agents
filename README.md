# Code Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

AI-powered code agent platform with a built-in CI/CD pipeline. Define agents in YAML, run them against any repo, and automate the full deployment cycle: **review → test → build → deploy → verify → rollback**.

## One-Command Install

```bash
curl -fsSL https://raw.githubusercontent.com/shivanshu1gupta-paytmpayments/code-agents/main/install.sh | bash
```

Then initialize in any project:

```bash
cd /path/to/your-project
code-agents init       # configure keys, write .env
code-agents start      # start the server
```

## What is this?

Code Agents lets you:

- **Define coding agents in YAML** — system prompt, model, backend, permissions — all configurable without code changes
- **Expose them as OpenAI-compatible endpoints** — any client that speaks the OpenAI API can use your agents
- **Use Cursor or Claude as the backend** — swap between `cursor-agent` and `claude-agent` per agent
- **Run a 6-step CI/CD pipeline** — connect repo → review code → run tests → build → deploy → verify → rollback
- **Integrate with Jenkins & ArgoCD** — trigger builds, monitor deployments, scan pod logs, auto-rollback
- **Stream tool activity** — see what tools the agent is using in real-time via `reasoning_content`
- **Manage sessions** — resume multi-turn conversations using session IDs

## CLI Commands

After installation, use these commands from any project directory:

### Getting Started

```bash
code-agents init              # Initialize in current repo (configure keys, write .env)
code-agents start             # Start the server (foreground)
code-agents start --bg        # Start the server (background)
code-agents setup             # Full interactive setup wizard
```

### Server Management

```bash
code-agents status            # Check server health and config
code-agents shutdown          # Stop the running server
code-agents logs              # Tail the log file (live)
code-agents logs 100          # Show last 100 lines
code-agents config            # Show .env configuration (secrets masked)
code-agents doctor            # Diagnose common issues
```

### Git Operations

```bash
code-agents branches          # List git branches
code-agents diff              # Diff current branch vs main
code-agents diff main feature # Diff between specific branches
```

### CI/CD Pipeline

```bash
code-agents test              # Run tests on current repo
code-agents test feature-123  # Run tests on a specific branch
code-agents review            # AI code review (HEAD vs main)
code-agents review main HEAD  # Review specific range

# Full pipeline management
code-agents pipeline start              # Start CI/CD pipeline
code-agents pipeline start feature-123  # Start for specific branch
code-agents pipeline status             # Show all pipeline runs
code-agents pipeline status abc123      # Status of specific run
code-agents pipeline advance abc123     # Advance to next step
code-agents pipeline rollback abc123    # Rollback deployment
```

### Other

```bash
code-agents agents            # List all 12 available agents
code-agents version           # Show version info
code-agents help              # Show all commands
```

## Quick Start (Manual)

### Prerequisites

- Python 3.10+
- [cursor-agent CLI](https://cursor.com/docs/cli): `curl https://cursor.com/install -fsS | bash`
- Active Cursor subscription (or Anthropic API key for claude backend)

### Install

```bash
git clone https://github.com/shivanshu1gupta-paytmpayments/code-agents.git
cd code-agents
poetry install
poetry install --with cursor    # Add cursor-agent SDK

# Go to your project and initialize
cd /path/to/your-project
code-agents init
```

### Run

```bash
# From your project directory (after init)
code-agents start              # Foreground mode
code-agents start --bg         # Background mode

# Or with custom host/port
HOST=127.0.0.1 PORT=9000 code-agents start
```

### Verify

```bash
code-agents status             # Check health
code-agents doctor             # Diagnose issues
curl http://localhost:8000/v1/agents      # List agents
curl http://localhost:8000/diagnostics    # Full diagnostics
```

## Included Agents (12)

| Agent | Description | Permissions |
|---|---|---|
| `agent-router` | Primary entry point: recommends which specialist to use | Read-only |
| `code-reasoning` | Analyzes codebases, explains architecture, traces data flows | Read-only |
| `code-writer` | Generates and modifies code based on requirements | Auto-approve edits |
| `code-reviewer` | Reviews code for bugs, security issues, and style | Read-only |
| `code-tester` | Tests codebases, writes tests, debugs and optimizes code | Auto-approve edits |
| `redash-query` | Queries databases via Redash: explores schemas, writes SQL | Read-only |
| `git-ops` | Git operations: branches, diffs, logs, push | Read-only |
| `test-coverage` | Runs tests, generates coverage, identifies gaps in new code | Auto-approve edits |
| `jenkins-build` | Triggers and monitors Jenkins CI build jobs | Read-only |
| `jenkins-deploy` | Triggers and monitors Jenkins deployment jobs | Read-only |
| `argocd-verify` | Verifies ArgoCD deployments, scans pod logs, rollbacks | Read-only |
| `pipeline-orchestrator` | Full CI/CD pipeline: review → test → build → deploy → verify → rollback | Read-only |

## CI/CD Pipeline

The 6-step deployment pipeline:

```
Step 1: Connect     → Verify repo, show branch diff
Step 2: Review/Test → AI code review + run tests + verify coverage
Step 3: Push/Build  → Push code, trigger Jenkins build
Step 4: Deploy      → Trigger Jenkins deployment job
Step 5: Verify      → Check ArgoCD pods, scan logs for errors
Step 6: Rollback    → Revert to previous revision (if anything fails)
```

### Pipeline REST API

| Endpoint | Description |
|----------|-------------|
| `POST /pipeline/start` | Start a pipeline run |
| `GET /pipeline/{id}/status` | Check pipeline status |
| `POST /pipeline/{id}/advance` | Advance to next step |
| `POST /pipeline/{id}/rollback` | Trigger rollback |
| `GET /pipeline/runs` | List all pipeline runs |

### CI/CD REST APIs

| Prefix | Endpoints | Description |
|--------|-----------|-------------|
| `/git/*` | branches, diff, log, push, status, fetch | Git operations |
| `/testing/*` | run, coverage, gaps | Test execution & coverage |
| `/jenkins/*` | build, status, log, wait | Jenkins CI/CD |
| `/argocd/*` | status, pods, logs, sync, rollback, history | ArgoCD |

## API Endpoints

### Chat Completions

```
POST /v1/agents/{agent_name}/chat/completions
POST /v1/chat/completions
```

OpenAI-compatible chat completion endpoint. Supports streaming and non-streaming.

### Other Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /v1/agents` | List all agents |
| `GET /v1/models` | OpenAI-compatible model listing |
| `GET /health` | Health check |
| `GET /diagnostics` | Runtime snapshot (no secrets) |
| `POST /redash/run-query` | Run SQL via Redash |
| `GET /elasticsearch/info` | Elasticsearch cluster info |

## Environment Variables

### Required (at least one backend)

| Variable | Description |
|----------|-------------|
| `CURSOR_API_KEY` | API key for cursor backend |
| `ANTHROPIC_API_KEY` | API key for claude backend |

### Server

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR |

### CI/CD Pipeline

| Variable | Description |
|----------|-------------|
| `TARGET_REPO_PATH` | Target repo path (auto-detected from cwd) |
| `JENKINS_URL` | Jenkins server URL |
| `JENKINS_USERNAME` | Jenkins API user |
| `JENKINS_API_TOKEN` | Jenkins API token |
| `JENKINS_BUILD_JOB` | Build job path (e.g. `pg2/pg2-dev-build-jobs`) |
| `JENKINS_DEPLOY_JOB` | Deploy job path |
| `ARGOCD_URL` | ArgoCD server URL |
| `ARGOCD_AUTH_TOKEN` | ArgoCD auth token |
| `ARGOCD_APP_NAME` | ArgoCD application name |

See `.env.example` for the full list including Elasticsearch, Atlassian OAuth, and Redash.

## Logging

Logs are written to both stderr and `logs/code-agents.log`:
- **Current file** contains only the last hour of data
- **Hourly rotation** to timestamped backups (e.g. `code-agents.log.2026-03-21_14`)
- **7 days** of hourly backups retained (168 files)

```bash
code-agents logs        # Tail live logs
tail -f logs/code-agents.log
```

## Testing

```bash
poetry run pytest              # Run all 47 tests
code-agents test               # Run tests on target repo
code-agents doctor             # Check setup
```

## Creating Custom Agents

Drop a YAML file in `agents/` and restart:

```yaml
name: my-agent
display_name: "My Custom Agent"
backend: cursor
model: "composer 1.5"
system_prompt: |
  You are a helpful coding assistant.
permission_mode: default
api_key: ${CURSOR_API_KEY}
cwd: "."
stream_tool_activity: true
include_session: true
```

Available at `POST /v1/agents/my-agent/chat/completions`.

## Open WebUI Integration

1. Start: `code-agents start`
2. In Open WebUI → Settings → Connections → OpenAI
3. URL: `http://localhost:8000/v1`, API Key: any string
4. All 12 agents appear as models in the dropdown

## Docker

```bash
docker build -t code-agents .
docker run -p 8000:8000 -e CURSOR_API_KEY=your-key code-agents
```

## Project Structure

```
code-agents/
  install.sh                    # One-command installer
  pyproject.toml                # Poetry config + CLI entry points
  agents/                       # YAML agent definitions (12 agents)
  code_agents/                  # Python package
    cli.py                      #   CLI: init, start, shutdown, status, diff, test, review, pipeline...
    setup.py                    #   Interactive setup wizard
    main.py                     #   Uvicorn server entry point
    app.py                      #   FastAPI app, CORS, lifespan, middleware
    config.py                   #   Settings + AgentLoader
    backend.py                  #   Backend abstraction (cursor/claude)
    stream.py                   #   SSE streaming + response builders
    models.py                   #   Pydantic request/response models
    logging_config.py           #   Hourly rotating file + console logging
    git_client.py               #   Async git operations client
    testing_client.py           #   Test runner + coverage parser
    jenkins_client.py           #   Jenkins REST API client
    argocd_client.py            #   ArgoCD REST API client
    pipeline_state.py           #   Pipeline state machine
    redash_client.py            #   Redash query client
    elasticsearch_client.py     #   Elasticsearch client
    atlassian_oauth.py          #   Atlassian OAuth 2.0
    routers/                    #   FastAPI route handlers
      completions.py            #     Chat completions API
      agents_list.py            #     Agent/model listing
      git_ops.py                #     /git/* endpoints
      testing.py                #     /testing/* endpoints
      jenkins.py                #     /jenkins/* endpoints
      argocd.py                 #     /argocd/* endpoints
      pipeline.py               #     /pipeline/* endpoints
      redash.py                 #     /redash/* endpoints
      elasticsearch.py          #     /elasticsearch/* endpoints
  tests/                        # 47 tests
  scripts/                      # Utility scripts
  initiater/                    # Project audit system (14 rules)
  logs/                         # Hourly-rotated log files
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
