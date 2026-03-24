# Agents

Code Agents ships with **12 pre-configured agents** in the `agents/` directory. Each is defined as a YAML file, exposed as an OpenAI-compatible endpoint, and available in the interactive chat.

**Quickest way to use any agent:**
```bash
code-agents chat          # pick from numbered menu
code-agents chat code-writer   # go straight to a specific agent
```

The chat auto-detects your git repo from the current directory, so the agent works on **your project's code** — not the code-agents source.

### Inline Agent Delegation

You don't need to switch agents to use them. From any active chat session, delegate a one-shot prompt to another agent:

```
you › /code-reviewer Review the auth module for security issues
  Delegating to code-reviewer: Review code for bugs, security issues, style violations
  code-reviewer › Looking at the auth module...
  (back to code-reasoning)

you › /code-tester Write unit tests for PaymentService
  Delegating to code-tester: Write tests, debug issues, optimize code quality
  code-tester › Creating tests for PaymentService...
  (back to code-reasoning)
```

- `/<agent> <prompt>` — sends a one-shot prompt, returns to your current agent
- `/<agent>` (no prompt) — switches permanently, same as `/agent <name>`
- **Tab-completion** — press Tab after `/` to autocomplete agent names and commands

---

## Agent Router

**File:** `agents/agent_router.yaml`
**Endpoint:** `/v1/agents/agent-router/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | default |

The entry point for users who are unsure which specialist to use. Asks 1-2 clarifying questions about the task, then recommends the appropriate specialist from all 13 agents (code-reasoning, code-writer, code-reviewer, code-tester, qa-regression, redash-query, git-ops, test-coverage, jenkins-build, jenkins-deploy, argocd-verify, pipeline-orchestrator) along with its endpoint URL. Does not perform deep analysis itself.

---

## Code Reasoning

**File:** `agents/code_reasoning.yaml`
**Endpoint:** `/v1/agents/code-reasoning/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | bypassPermissions (read-only) |

Read-only code analysis agent. Use it to:

- Explain architecture and design patterns
- Trace data flows through the codebase
- Compare approaches and analyze complexity
- Plan testing strategies
- Answer "how does this work?" questions

This agent cannot modify files — it only reads and reasons.

---

## Code Writer

**File:** `agents/code_writer.yaml`
**Endpoint:** `/v1/agents/code-writer/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | acceptEdits (auto-approve) |

Generates and modifies code. Use it to:

- Write new files, modules, and tests
- Refactor existing code
- Implement features from requirements
- Apply fixes

File edits are auto-approved — no user confirmation required.

---

## Code Reviewer

**File:** `agents/code_reviewer.yaml`
**Endpoint:** `/v1/agents/code-reviewer/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | default |

Critical code review without rewriting. Use it to:

- Identify bugs and security issues
- Suggest performance improvements
- Flag style violations
- Review test quality and coverage gaps
- Prioritize issues by severity with concrete examples

---

## Code Tester

**File:** `agents/code_tester.yaml`
**Endpoint:** `/v1/agents/code-tester/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | acceptEdits |

Testing, debugging, and code quality. Use it to:

- Write and refactor tests
- Debug issues using debugger tools
- Optimize performance
- Improve readability and maintainability

---

## Redash Query

**File:** `agents/redash_query.yaml`
**Endpoint:** `/v1/agents/redash-query/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | default |

Database query agent powered by Redash. Use it to:

- List available data sources (databases/shards)
- Explore table schemas (tables + columns)
- Write SQL queries from natural language prompts
- Execute queries and get formatted results
- Iterate on queries based on results or errors

Requires `REDASH_BASE_URL` and either `REDASH_API_KEY` or `REDASH_USERNAME` + `REDASH_PASSWORD` in `.env`.

---

## Git Operations

**File:** `agents/git_ops.yaml`
**Endpoint:** `/v1/agents/git-ops/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | default |

Git operations on a target repository. Use it to:

- List branches and show current branch
- Show diffs between branches (feature vs main)
- View commit history
- Push branches to remote
- Check working tree status

Requires `TARGET_REPO_PATH` in `.env`.

---

## Test Coverage

**File:** `agents/test_coverage.yaml`
**Endpoint:** `/v1/agents/test-coverage/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | acceptEdits |

Test execution and coverage analysis. Use it to:

- Run test suites (auto-detects pytest, jest, maven, gradle, go)
- Generate and parse coverage reports
- Identify new code lacking test coverage
- Report coverage percentages and uncovered lines
- Block pipeline if coverage is below threshold

Requires `TARGET_REPO_PATH` in `.env`. Optional: `TARGET_TEST_COMMAND`, `TARGET_COVERAGE_THRESHOLD`.

---

## Jenkins Build

**File:** `agents/jenkins_build.yaml`
**Endpoint:** `/v1/agents/jenkins-build/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | default |

Jenkins CI build agent. Use it to:

- Trigger Jenkins build jobs for a branch
- Monitor build status (queued, building, success, failure)
- Fetch build logs and console output
- Report build results and duration

Requires `JENKINS_URL`, `JENKINS_USERNAME`, `JENKINS_API_TOKEN` in `.env`.

---

## Jenkins Deploy

**File:** `agents/jenkins_deploy.yaml`
**Endpoint:** `/v1/agents/jenkins-deploy/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | default |

Jenkins deployment agent. Use it to:

- Trigger deployment jobs with specific build numbers
- Monitor deployment progress
- Fetch deployment logs
- Report deployment outcomes

Requires `JENKINS_URL`, `JENKINS_USERNAME`, `JENKINS_API_TOKEN` in `.env`.

---

## ArgoCD Verify

**File:** `agents/argocd_verify.yaml`
**Endpoint:** `/v1/agents/argocd-verify/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | default |

ArgoCD deployment verification and rollback. Use it to:

- Check application sync and health status
- List pods and verify correct image tags/build numbers
- Fetch pod logs and scan for errors (ERROR, FATAL, Exception, panic)
- Trigger rollback to previous deployment revision
- View deployment history

Requires `ARGOCD_URL`, `ARGOCD_AUTH_TOKEN` in `.env`.

---

## QA Regression

**File:** `agents/qa_regression.yaml`
**Endpoint:** `/v1/agents/qa-regression/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | acceptEdits |

Principal QA engineer agent that eliminates manual testing. Use it to:

- Run the full regression test suite and report pass/fail/coverage
- Write missing tests by analyzing the codebase (reads CLAUDE.md/README.md for context)
- Mock all external dependencies (APIs, databases, message queues)
- Identify untested code paths and coverage gaps
- Create test plans for critical flows
- Ensure every feature has automated regression coverage before release

Reads the project's CLAUDE.md or README.md to understand architecture before writing tests. Uses the project's existing test framework (pytest, jest, JUnit, Go test).

---

## Pipeline Orchestrator

**File:** `agents/pipeline_orchestrator.yaml`
**Endpoint:** `/v1/agents/pipeline-orchestrator/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | default |

Full CI/CD pipeline orchestrator. Guides users through the 6-step deployment process:

1. **Connect** — Verify repo access, show branch and changes
2. **Review & Test** — Code review + run tests + verify coverage
3. **Push & Build** — Push code, trigger Jenkins build
4. **Deploy** — Trigger Jenkins deployment
5. **Verify** — Check ArgoCD pods, scan logs
6. **Rollback** — Revert if anything fails

Also available as a REST API: `POST /pipeline/start`, `GET /pipeline/{id}/status`, `POST /pipeline/{id}/advance`, `POST /pipeline/{id}/rollback`.

Requires `TARGET_REPO_PATH` and optionally `JENKINS_*` and `ARGOCD_*` env vars.

---

## Creating a Custom Agent

Add a YAML file to the `agents/` directory and restart the server. Full schema:

```yaml
name: my-agent                          # Required: URL-safe identifier
display_name: "My Custom Agent"         # Optional: UI name (defaults to name)
backend: cursor                         # Optional: "cursor" or "claude" (default: cursor)
model: "composer 1.5"                   # Optional: LLM model ID
system_prompt: |                        # Optional: supports ${ENV_VAR} expansion
  You are a helpful assistant.
permission_mode: default                # Optional: "default" | "acceptEdits" | "bypassPermissions"
cwd: "."                                # Optional: working directory
api_key: ${CURSOR_API_KEY}              # Optional: API key (env var expansion)
stream_tool_activity: true              # Optional: show tool calls in reasoning_content
include_session: true                   # Optional: return session_id for multi-turn
extra_args:                             # Optional: backend-specific arguments
  mode: ask
```

### Permission Modes

| Mode | Behavior |
|---|---|
| `default` | Agent asks before making changes |
| `acceptEdits` | Auto-approve all file modifications |
| `bypassPermissions` | Read-only, no modifications allowed |

### Claude Backend Options

**Option A: Claude CLI (recommended — uses your subscription, no API key)**
```bash
code-agents init --backend
# Choose: 3. Claude CLI (uses your Claude subscription)
# Or set manually in ~/.code-agents/config.env:
CODE_AGENTS_BACKEND=claude-cli
CODE_AGENTS_CLAUDE_CLI_MODEL=claude-sonnet-4-6
```
Requires: Claude CLI installed and logged in. Uses Claude Pro/Max subscription.

**Option B: Claude API (pay-as-you-go with API key)**

1. Set `ANTHROPIC_API_KEY` (via `code-agents init` or in `~/.code-agents/config.env`)
2. Rename the example: `mv agents/claude_example.yaml.disabled agents/claude_example.yaml`
3. Restart the server

`claude-agent-sdk` is a core dependency — no extra install step needed.

---

## Agent Resolution

When a request comes in, the server resolves the target agent using this fallback chain:

1. Exact agent `name` match
2. `display_name` match
3. `model` ID match (normalized: hyphens ↔ spaces)
4. Default to first loaded agent

This means clients can reference agents by name, display name, or model ID interchangeably.

---

## Multi-Turn Sessions

All agents support multi-turn conversations. **The easiest way is via chat** — sessions are managed automatically:

```bash
code-agents chat code-reasoning
# Sessions auto-save to ~/.code-agents/chat_history/ with unique UUIDs.
# Use /session to see current ID, /clear to start fresh.
# Use /history to list saved sessions, /resume <id> to continue one.
# Or: code-agents sessions / code-agents chat --resume <id>
```

**Via API** — pass `session_id` manually:

```bash
# First request — get a session_id back
RESPONSE=$(curl -s -X POST http://localhost:8000/v1/agents/code-reasoning/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Explain the auth module"}]}')

SESSION_ID=$(echo $RESPONSE | jq -r '.session_id')

# Follow-up — pass session_id to continue the conversation
curl -X POST http://localhost:8000/v1/agents/code-reasoning/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"messages\": [{\"role\": \"user\", \"content\": \"Now explain the middleware\"}], \"session_id\": \"$SESSION_ID\"}"
```

---

## Typical Workflow

### Via Interactive Chat (recommended)

```
$ code-agents chat

  Select an agent:
    1.  code-reasoning     Analyze code, explain architecture
    2.  code-writer        Write/modify code, refactor
    3.  code-reviewer      Review for bugs, security, style
    4.  code-tester        Write tests, debug issues
    ...13 agents total

  Pick agent [1-12]: 1

  you › Explain the payment flow
  code-reasoning › The payment flow starts at...

  you › /agent code-tester
  ✓ Switched to: code-tester

  you › Write tests for PaymentService
  code-tester › Creating tests...
```

Chat commands: `/help /quit /agent <name> /agents /rules /run <cmd> /exec <cmd> /restart /session /clear /history /resume <id> /delete-chat <id> /<agent> <prompt>`

The agent automatically works on **your current project** (detects git repo from cwd).
If the server isn't running, chat offers to start it for you.

### Agent Rules

You can configure persistent rules that get injected into agent system prompts. Rules are markdown files — simple, no special syntax.

**Create rules:**
```bash
code-agents rules create                      # project rule, all agents
code-agents rules create --agent code-writer  # project rule, specific agent
code-agents rules create --global             # global rule, all agents
```

**File structure:**
```
~/.code-agents/rules/                  ← global (all projects)
    _global.md                         ← all agents
    code-writer.md                     ← only code-writer

myrepo/.code-agents/rules/             ← project (this repo only)
    _global.md                         ← all agents in this repo
    code-reviewer.md                   ← only code-reviewer in this repo
```

**Auto-refresh:** Rules are read from disk on every message. Edit a rule file in another terminal mid-chat — the next message picks up the change immediately.

**In chat:** `/rules` shows which rules are active for the current agent.

### Via API / Open WebUI

```
Agent Router  ──→  clarifies task
    │
    ├──→  Code Reasoning        (understand)
    ├──→  Code Writer            (implement)
    ├──→  Code Reviewer          (review)
    ├──→  Code Tester            (test & debug)
    ├──→  Redash Query           (database queries)
    ├──→  Git Ops                (branches, diffs, push)
    ├──→  Test Coverage          (run tests, coverage gaps)
    ├──→  Jenkins Build          (CI builds)
    ├──→  Jenkins Deploy         (deployments)
    ├──→  ArgoCD Verify          (pod health, rollback)
    └──→  Pipeline Orchestrator  (full CI/CD pipeline)
```

Use `code-agents curls <agent-name>` to get copy-pasteable curl commands for any agent.

---

## Maintenance

When you add a new agent, workflow, or integration to the project:

1. Add the agent YAML to `agents/`
2. Document it in this file (`Agents.md`) following the format above
3. Add role description to `AGENT_ROLES` dict in `code_agents/chat.py`
4. Add example prompts to `_AGENT_EXAMPLES` dict in `code_agents/cli.py` (for `code-agents curls <agent>`)
5. **Update `agents/agent_router.yaml`** — add to specialists list in system prompt
6. **Update `README.md`** — agents table, project structure
7. **Update `CLAUDE.md`** and `cursor.md` — architecture section
8. **Add tests** in `tests/` for any new functionality

Run `poetry run python initiater/run_audit.py --rules workflow` to verify sync.
Run `poetry run pytest` to verify all 201 tests pass.

### Key files that reference agent lists
- `agents/agent_router.yaml` — system prompt lists all specialists
- `code_agents/chat.py` — `AGENT_ROLES` dict (roles shown in chat)
- `code_agents/cli.py` — `_AGENT_EXAMPLES` dict (example curls per agent), help text
- `README.md` — agents table
- `Agents.md` — this file
- `CLAUDE.md` / `cursor.md` — architecture sections

### Copyright
Copyright (c) 2026 Paytm Payments Services Limited (Regulated by RBI)