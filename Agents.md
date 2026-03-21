# Agents

Code Agents ships with twelve pre-configured agents in the `agents/` directory. Each is defined as a YAML file and exposed as an OpenAI-compatible endpoint.

---

## Agent Router

**File:** `agents/agent_router.yaml`
**Endpoint:** `/v1/agents/agent-router/chat/completions`

| Field | Value |
|---|---|
| Backend | Cursor |
| Model | composer 1.5 |
| Permission Mode | default |

The entry point for users who are unsure which specialist to use. Asks 1-2 clarifying questions about the task, then recommends the appropriate agent (code-reasoning, code-writer, code-reviewer, code-tester, or redash-query) along with its endpoint URL. Does not perform deep analysis itself.

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

### Claude Backend Example

A disabled example is included at `agents/claude_example.yaml.disabled`. To use the Claude backend:

1. Install Claude dependencies: `poetry install --with claude`
2. Set `ANTHROPIC_API_KEY`
3. Create an agent YAML with `backend: claude` and a Claude model (e.g., `sonnet`)

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

All agents support multi-turn conversations via `session_id`:

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

```
User question
    │
    ▼
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

Use the router for triage, or call specialist agents directly if you already know what you need.

---

## Maintenance

When you add a new agent, workflow, or integration to the project:

1. Add the agent YAML to `agents/`
2. Document it in this file (`Agents.md`) following the format above
3. **Update `README.md`** — specifically:
   - The **Included Agents** table under "Creating Agents"
   - The **Option B connections table** under "Open WebUI Integration" (if applicable)
   - The **Project Structure** tree at the bottom
   - Any other sections that reference the agent list

Keeping both files in sync ensures users discover all available agents regardless of which doc they read first.