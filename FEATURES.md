# Code Agents — Feature History

A chronological record of every feature built, from the first line of code to where we are today. Every item here was designed, implemented, tested, and documented in this project.

---

## Phase 1: Interactive Chat Foundation

### 1. Inline Agent Delegation
**What:** Type `/<agent> <prompt>` to send a one-shot prompt to another agent without leaving your current session.
```
you › /code-reviewer Review the auth module for security issues
  Delegating to code-reviewer...
  code-reviewer › Found 3 security issues...
  (back to code-reasoning)
```
**Why:** No more switching agents just to ask a quick question.

### 2. Tab-Completion in Chat REPL
**What:** Press Tab after `/` to autocomplete slash commands and agent names. Also works after `/agent ` to complete agent names.
```
/co<Tab>  → /code-reasoning, /code-writer, /code-tester, /code-reviewer
/agent co<Tab>  → code-reasoning, code-writer, ...
```
**Why:** Stop typing full agent names. Discover commands without /help.

### 3. Readline ANSI Fix
**What:** Fixed tab-completion on macOS by wrapping ANSI escape codes in readline invisible markers.
**Why:** Colors in the prompt broke cursor position tracking, preventing Tab from working.

---

## Phase 2: Workspace & Configuration

### 4. Cursor Workspace Trust Detection
**What:** Detect "Workspace Trust Required" errors at boot time and auto-trust via `cursor-agent --trust`.
**Why:** Users were hitting cryptic errors mid-conversation. Now it's handled before chat starts.

### 5. Centralized .env Configuration
**What:** Two-tier config system:
- Global: `~/.code-agents/config.env` (API keys, server, integrations)
- Per-repo: `.env.code-agents` (Jenkins, ArgoCD, testing)
**Why:** No more per-repo `.env` files conflicting with repos that use `.env/` as a virtualenv directory.

### 6. Migration Command
**What:** `code-agents migrate` — splits a legacy `.env` into global + per-repo files automatically.
**Why:** Smooth upgrade path for existing users.

### 7. Init Section Flags
**What:** `code-agents init --jenkins` to update just Jenkins config, `--argocd` for ArgoCD, etc.
**Why:** Don't re-run the full wizard just to change one setting.

---

## Phase 3: Command Execution Engine

### 8. Command Detection from Agent Responses
**What:** Agent outputs ```bash blocks → detected, shown in red box, user prompted to run.
**Why:** Agents suggest commands — now you can execute them without copy-pasting.

### 9. Backslash Line Continuation
**What:** Multi-line curl commands with `\` are detected as one command, not three separate lines.
**Why:** Real-world curls span multiple lines. They should be treated as one command.

### 10. Placeholder Resolution
**What:** `{job_name}` and `<DATA_SOURCE_ID>` in commands → user prompted to fill in values.
**Why:** Agent outputs templates with placeholders. Now they're interactive.

### 11. Red Bordered Output Box
**What:** Command output displayed in a red-bordered box with JSON pretty-printing.
```
  ┌──────────────────────────────────────┐
  │ $ curl -s http://127.0.0.1:8000/...  │
  ├──────────────────────────────────────┤
  │ { "status": "ok" }                   │
  │ ✓ Done                               │
  └──────────────────────────────────────┘
```
**Why:** Clean visual separation between agent text and command output.

### 12. Clipboard Copy
**What:** Command output auto-copied to clipboard (macOS pbcopy).
**Why:** Large JSON responses are easier to work with when already in clipboard.

---

## Phase 4: Agent Rules System

### 13. Two-Tier Rules
**What:** Markdown files injected into agent system prompts:
- Global: `~/.code-agents/rules/_global.md`
- Per-agent: `~/.code-agents/rules/code-writer.md`
- Project: `{repo}/.code-agents/rules/`
**Why:** Persistent instructions that survive across chat sessions.

### 14. Auto-Refresh Rules
**What:** Rules read from disk on every message — edit a file mid-chat, next message picks it up.
**Why:** No restart needed. Edit rules in another terminal while chatting.

### 15. Rules CLI
**What:** `code-agents rules list`, `create`, `edit`, `delete` — manage rules from the terminal.
**Why:** Easy CRUD without manually creating files.

### 16. Auto-Save Approved Commands
**What:** When you approve a command (choose 1. Yes), it's auto-saved to the agent's rules. Next time → auto-approved.
**Why:** Approve once, run forever. No repeated confirmations for trusted commands.

---

## Phase 5: Agentic Loop

### 17. Command Output → Agent Feedback
**What:** After running a command, output is automatically sent back to the agent. Agent continues reasoning.
**Why:** The agent sees the curl result and suggests the next step — like a real assistant.

### 18. /exec Command
**What:** `/exec <cmd>` runs a command AND feeds output to the agent (unlike `/run` which is silent).
**Why:** Manually execute something and get the agent's analysis immediately.

### 19. Bash Tool in System Prompt
**What:** All agents know they can request running commands via ```bash blocks.
**Why:** Agent was saying "I cannot reach the server" instead of outputting a curl for the user to run.

### 20. One Command at a Time
**What:** System prompt tells agent to output exactly ONE ```bash block per response and STOP.
**Why:** Matches Claude Code's workflow — propose, approve, execute, continue.

---

## Phase 6: Claude Code-Style UX

### 21. Spinner with Live Timer
**What:** Animated spinner while waiting: `⠹ Thinking... 12s`. Shows elapsed time after response: `✻ Response took 2m 23s`.
**Why:** Know if the agent is working or stuck.

### 22. Green BASH Indicator
**What:** `● BASH running...` shown when executing a command.
**Why:** Clear visual that a command is active.

### 23. 1. Yes / 2. No Selector
**What:** Numbered options for command approval (default: Yes, just press Enter).
```
  Run this command?
    1. Yes
    2. No
  Choose [1/2]:
```
**Why:** Cleaner than `[y/N/all/skip]`. Default-yes for fast workflows.

### 24. Full Command Display (No Truncation)
**What:** Long commands wrap across multiple lines in the approval box — no more `...` truncation.
**Why:** See exactly what you're about to run before approving.

### 25. Auto-Collapse Long Responses
**What:** Responses >25 lines collapse to first 8 + last 8 lines. Press Ctrl+O to expand in pager.
**Why:** Chat stays clean. Long outputs don't push your prompt offscreen.

### 26. Markdown Rendering
**What:** `**bold**` → bold, `` `code` `` → cyan, `## Header` → bold in terminal.
**Why:** Agent responses look better without raw markdown syntax.

---

## Phase 7: Agent Welcome Messages

### 27. Welcome Boxes
**What:** When selecting or switching to an agent, a red-bordered box shows what it can do:
```
  ┌──────────────────────────────────────────┐
  │ Code Tester — Testing & Debugging        │
  ├──────────────────────────────────────────┤
  │ What I can do:                           │
  │   • Write unit tests and fixtures        │
  │   • Debug failing tests                  │
  │ Try asking:                              │
  │   "Write unit tests for PaymentService"  │
  └──────────────────────────────────────────┘
```
**Why:** New users know what each agent does without reading docs.

---

## Phase 8: Jenkins Integration

### 28. Job Discovery
**What:** `GET /jenkins/jobs?folder=pg2/pg2-dev-build-jobs` — list all jobs in a folder.
**Why:** Don't guess job names. Browse what's available.

### 29. Parameter Introspection
**What:** `GET /jenkins/jobs/{path}/parameters` — fetch parameter definitions (name, type, default, choices).
**Why:** Know exactly what the build job expects before triggering.

### 30. Build-and-Wait
**What:** `POST /jenkins/build-and-wait` — trigger build, poll until complete, extract build version from logs.
**Why:** One call does everything: trigger → poll → extract version for deploy.

### 31. Build Version Extraction
**What:** Regex patterns scan console output for Docker tags, Maven versions, `BUILD_VERSION=`, etc.
**Why:** The deploy job needs the build version — now it's extracted automatically.

### 32. Folder Job Path Handling
**What:** `_job_path()` converts `pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz` → correct Jenkins API path. Strips accidental `job/` prefixes.
**Why:** Users copy-paste from Jenkins URLs which have `job/` prefixes.

---

## Phase 9: Agent Quality

### 33. Rewritten System Prompts
**What:** All 4 core agents (reasoning, writer, reviewer, tester) rewritten with:
- Role definition ("You are a senior X agent")
- Step-by-step methodology
- Quality standards
- Explicit boundaries (what NOT to do)
**Why:** Generic 3-line prompts → detailed 30-line prompts = much better agent behavior.

### 34. QA Regression Agent (13th agent)
**What:** Principal QA engineer that runs regression suites, writes missing tests, mocks dependencies.
**Why:** Eliminate manual QA testing. Every feature should have automated coverage.

---

## Phase 10: Backend & Infrastructure

### 35. Claude CLI Backend
**What:** `CODE_AGENTS_BACKEND=claude-cli` — use your Claude Pro/Max subscription instead of API key.
**Why:** No `ANTHROPIC_API_KEY` needed. Uses the `claude` CLI binary with your subscription auth.

### 36. claude-agent-sdk as Core Dependency
**What:** Moved from optional (`poetry install --with claude`) to core dependency.
**Why:** Always available. No extra install step.

### 37. code-agents update
**What:** `code-agents update` — git pull + poetry install in one command. SSH→HTTPS fallback.
**Why:** Easy updates without remembering the install directory.

### 38. code-agents restart
**What:** `code-agents restart` — shutdown + start in one command. Also `/restart` in chat.
**Why:** Config changes need a restart. One command instead of two.

### 39. Shell Tab-Completion
**What:** `code-agents ru<Tab>` → `rules`. `code-agents rules create --agent <Tab>` → agent names.
**Why:** Discover subcommands and flags without reading help.

### 40. Makefile
**What:** 40+ make targets: `make test`, `make chat`, `make start`, `make doctor`, etc.
**Why:** Standard development workflow. `make help` shows everything.

---

## Phase 11: Code Quality

### 41. 10-Bug Code Review Hunt
**What:** Found and fixed 10 real bugs:
- Placeholder commands saved unresolved to rules
- Jenkins `_job_path` stripping legitimate "job" folders
- Shallow copy mutations leaking across requests
- Race conditions in rules file read/write (fixed with fcntl locking)
- Misleading env load precedence docs
**Why:** Ship quality. Every bug fixed makes the tool more reliable.

### 42. Chat History Persistence
**What:** Sessions auto-save to `~/.code-agents/chat_history/`. Resume with `--resume <id>` or `/resume`.
**Why:** Don't lose your conversation. Pick up where you left off.

---

## Stats

| Metric | Count |
|--------|-------|
| Commits | 68 |
| Files changed | 38 |
| Tests | 230 |
| Agents | 13 |
| CLI commands | 23 |
| Chat slash commands | 14 |
| Backends | 3 (cursor, claude API, claude CLI) |
| Make targets | 40+ |

---

*Built with Claude Code — every feature designed, implemented, tested, and documented in conversation.*
