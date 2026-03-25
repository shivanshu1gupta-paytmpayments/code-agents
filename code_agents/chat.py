"""
Interactive CLI chat REPL for Code Agents.

Supports all 12 agents — each stays in its role. Switch agents mid-session
with /agent <name>. Streams responses in real-time.

Usage:
    code-agents chat                    # default: code-reasoning
    code-agents chat code-writer        # specific agent
    code-agents chat --agent code-tester
"""

from __future__ import annotations

import json
import os
import re
import sys
import time as _time_mod
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Colors (same as setup.py, no deps)
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty()


def _w(code: str, t: str) -> str:
    return f"\033[{code}m{t}\033[0m" if _USE_COLOR else t


def bold(t: str) -> str: return _w("1", t)
def green(t: str) -> str: return _w("32", t)
def yellow(t: str) -> str: return _w("33", t)
def red(t: str) -> str: return _w("31", t)
def cyan(t: str) -> str: return _w("36", t)
def dim(t: str) -> str: return _w("2", t)
def magenta(t: str) -> str: return _w("35", t)


def _rl_wrap(code: str, t: str) -> str:
    """Wrap ANSI escape in readline invisible markers (\x01..\x02) for prompts."""
    if not _USE_COLOR:
        return t
    return f"\x01\033[{code}m\x02{t}\x01\033[0m\x02"


def _rl_bold(t: str) -> str: return _rl_wrap("1", t)
def _rl_green(t: str) -> str: return _rl_wrap("32", t)


# ---------------------------------------------------------------------------
# Agent role descriptions (extracted from YAML system prompts)
# ---------------------------------------------------------------------------

AGENT_ROLES = {
    "code-reasoning": "Analyze code, explain architecture, trace flows (read-only)",
    "code-writer": "Generate and modify code, refactor, implement features",
    "code-reviewer": "Review code for bugs, security issues, style violations",
    "code-tester": "Write tests, debug issues, optimize code quality",
    "redash-query": "Write SQL, query databases, explore schemas via Redash",
    "git-ops": "Git operations: branches, diffs, logs, push",
    "test-coverage": "Run test suites, generate coverage reports, find gaps",
    "jenkins-build": "Trigger and monitor Jenkins CI build jobs",
    "jenkins-deploy": "Trigger and monitor Jenkins deployment jobs",
    "argocd-verify": "Verify ArgoCD deployments, scan pod logs, rollback",
    "pipeline-orchestrator": "Guide full CI/CD pipeline end-to-end",
    "qa-regression": "Run regression suites, write missing tests, eliminate manual QA",
    "auto-pilot": "Autonomous orchestrator — delegates to sub-agents, runs full workflows",
    "agent-router": "Help pick the right specialist agent",
}

AGENT_WELCOME = {
    "code-reasoning": (
        "Code Reasoning — Read-Only Analysis",
        [
            "Explain architecture and design patterns",
            "Trace data flows through the codebase",
            "Compare approaches and analyze complexity",
            "Answer 'how does this work?' questions",
        ],
        [
            "Explain the authentication flow in this project",
            "How does the payment processing pipeline work?",
            "What design patterns are used in the routers?",
        ],
    ),
    "code-writer": (
        "Code Writer — Generate & Modify Code",
        [
            "Write new files, modules, and functions",
            "Refactor existing code for clarity",
            "Implement features from requirements",
            "Apply fixes and improvements",
        ],
        [
            "Add input validation to the login function",
            "Refactor the UserService to use dependency injection",
            "Create a retry mechanism for failed API calls",
        ],
    ),
    "code-reviewer": (
        "Code Reviewer — Critical Review",
        [
            "Identify bugs and security vulnerabilities",
            "Suggest performance improvements",
            "Flag style violations and anti-patterns",
            "Review test quality and coverage gaps",
        ],
        [
            "Review the auth module for security issues",
            "Check the new payment endpoint for bugs",
            "Review the last 3 commits for quality",
        ],
    ),
    "code-tester": (
        "Code Tester — Testing & Debugging",
        [
            "Write unit tests, integration tests, and fixtures",
            "Debug failing tests and trace issues",
            "Optimize code quality and readability",
            "Refactor test suites for better coverage",
        ],
        [
            "Write unit tests for the PaymentService class",
            "Debug why test_auth_flow is failing",
            "Add edge case tests for the retry logic",
        ],
    ),
    "redash-query": (
        "Redash Query — SQL & Database Explorer",
        [
            "List available data sources and schemas",
            "Write SQL queries from natural language",
            "Execute queries and format results",
            "Explore table structures and relationships",
        ],
        [
            "Show me all data sources available",
            "Write a query for the top 10 users by order count",
            "What tables are in the acqcore0 database?",
        ],
    ),
    "git-ops": (
        "Git Operations — Branches, Diffs, Logs",
        [
            "List branches and show current branch",
            "Show diffs between branches",
            "View commit history and logs",
            "Check working tree status",
        ],
        [
            "Show the last 10 commits",
            "What changed between main and this branch?",
            "List all branches with their last commit date",
        ],
    ),
    "test-coverage": (
        "Test Coverage — Run Tests & Analyze Gaps",
        [
            "Run test suites (auto-detects pytest/jest/maven/go)",
            "Generate coverage reports",
            "Identify new code lacking test coverage",
            "Report coverage percentages by file",
        ],
        [
            "Run tests and show coverage report",
            "Which files have less than 80% coverage?",
            "Show uncovered lines in the auth module",
        ],
    ),
    "jenkins-build": (
        "Jenkins Build — CI Build Jobs",
        [
            "Trigger Jenkins build jobs for a branch",
            "Monitor build status in real-time",
            "Fetch build logs and console output",
            "Report build results and duration",
        ],
        [
            "Trigger a build for the feature/auth branch",
            "What's the status of the last build?",
            "Show me the build logs for build #42",
        ],
    ),
    "jenkins-deploy": (
        "Jenkins Deploy — Deploy Services to Environments",
        [
            "Deploy a service with a specific build version (image_tag)",
            "Choose target environment: dev, dev1, dev2, dev-stable",
            "Monitor deployment progress with live polling",
            "Recommend ArgoCD verification after success",
        ],
        [
            "Deploy pg-acquiring-biz with build version 1.2.3 to dev",
            "Deploy the latest build to dev-stable",
            "What environments are available for deployment?",
        ],
    ),
    "argocd-verify": (
        "ArgoCD Verify — Deployment Verification",
        [
            "Check application sync and health status",
            "List pods and verify image tags",
            "Scan pod logs for errors (ERROR, FATAL, panic)",
            "Trigger rollback to previous revision",
        ],
        [
            "Are all pods healthy after the latest deploy?",
            "Check pod logs for any errors",
            "Rollback to the previous deployment",
        ],
    ),
    "pipeline-orchestrator": (
        "Pipeline Orchestrator — Full CI/CD Pipeline",
        [
            "Guide through 6-step deployment pipeline",
            "Connect → Review/Test → Build → Deploy → Verify → Rollback",
            "Coordinate across Jenkins, ArgoCD, and git",
            "End-to-end deployment automation",
        ],
        [
            "Start the deployment pipeline for this branch",
            "What's the status of the current pipeline?",
            "Walk me through deploying to production",
        ],
    ),
    "qa-regression": (
        "QA Regression — Eliminate Manual Testing",
        [
            "Run full regression test suite and report results",
            "Write missing tests by analyzing the codebase",
            "Mock external dependencies (APIs, DBs, queues)",
            "Identify untested code paths and coverage gaps",
            "Create test plans for critical flows",
        ],
        [
            "Run the full regression suite and report what's failing",
            "Write tests for all untested code in src/services/",
            "What's the current test coverage? Where are the gaps?",
            "Create integration tests for the payment API endpoints",
        ],
    ),
    "auto-pilot": (
        "Auto-Pilot — Full Autonomy",
        [
            "Execute multi-step workflows end-to-end autonomously",
            "Delegate to 13 specialist agents (code-writer, reviewer, tester, etc.)",
            "Build → Deploy → Verify pipelines without manual switching",
            "Run code reviews, apply fixes, and re-verify automatically",
            "Query databases, check git status, run tests — all in one flow",
        ],
        [
            "Build and deploy pg-acquiring-biz to dev",
            "Review the latest changes, fix issues, and run tests",
            "Run the full CI/CD pipeline for release branch",
            "Check what changed since last deploy, review, and build",
        ],
    ),
    "agent-router": (
        "Agent Router — Find the Right Specialist",
        [
            "Recommend which agent to use for your task",
            "Ask clarifying questions to understand your needs",
            "Explain what each specialist agent does",
            "Route you to the best agent for the job",
        ],
        [
            "I need to fix a bug in the payment module",
            "Help me set up CI/CD for this project",
            "I want to understand how the auth system works",
        ],
    ),
}


_ANSI_STRIP_RE = re.compile(r"\033\[[0-9;]*m")


def _spinner(message: str):
    """Context manager that shows a spinner while waiting. Like Claude CLI's 'thinking...'."""
    import threading
    import itertools

    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    stop_event = threading.Event()

    def _spin():
        for frame in itertools.cycle(frames):
            if stop_event.is_set():
                break
            sys.stdout.write(f"\r  {yellow(frame)} {dim(message)}")
            sys.stdout.flush()
            stop_event.wait(0.1)
        # Clear the spinner line
        sys.stdout.write(f"\r{' ' * (len(message) + 10)}\r")
        sys.stdout.flush()

    class _SpinnerCtx:
        def __enter__(self):
            self._thread = threading.Thread(target=_spin, daemon=True)
            self._thread.start()
            return self

        def __exit__(self, *args):
            stop_event.set()
            self._thread.join(timeout=1)

    return _SpinnerCtx()


import fcntl


def _save_command_to_rules(cmd: str, agent_name: str, repo_path: str) -> None:
    """Save an executed command to the agent's project rules file (file-locked)."""
    from .rules_loader import PROJECT_RULES_DIRNAME
    rules_dir = Path(repo_path) / PROJECT_RULES_DIRNAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / f"{agent_name}.md"

    try:
        # Use file lock to prevent race conditions
        with open(str(rules_file), "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                existing = f.read()

                if cmd in existing:
                    print(dim("  (command already in rules)"))
                    return

                if "## Saved Commands" not in existing:
                    f.write("\n\n## Saved Commands\nThese commands have been approved and can be auto-run.\n")
                f.write(f"\n```bash\n{cmd}\n```\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        print(green(f"  ✓ Saved to {rules_file}"))
    except OSError as e:
        print(yellow(f"  ! Could not save to rules: {e}"))


def _is_command_trusted(cmd: str, agent_name: str, repo_path: str) -> bool:
    """Check if a command is in the agent's saved/trusted commands (file-locked)."""
    from .rules_loader import PROJECT_RULES_DIRNAME
    rules_file = Path(repo_path) / PROJECT_RULES_DIRNAME / f"{agent_name}.md"
    if not rules_file.is_file():
        return False
    try:
        with open(str(rules_file), "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                content = f.read()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return cmd in content
    except OSError:
        return False


def _ask_yes_no(prompt_text: str, default: bool = True) -> bool:
    """Interactive Yes/No prompt with numbered options. Returns True for Yes."""
    print(f"  {bold(prompt_text)}")
    print(f"    {bold('1.')} Yes")
    print(f"    {bold('2.')} No")

    try:
        answer = input(f"  {dim('Choose [1/2]')}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if not answer:
        return default
    if answer in ("1", "y", "yes"):
        return True
    if answer in ("2", "n", "no"):
        return False
    return default


def _render_markdown(text: str) -> str:
    """Render basic markdown to terminal ANSI: **bold**, `code`, ## headers."""
    if not _USE_COLOR:
        return text
    # Bold: **text** → ANSI bold
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: bold(m.group(1)), text)
    # Inline code: `text` → cyan
    text = re.sub(r'`([^`]+)`', lambda m: cyan(m.group(1)), text)
    # Headers: ## Title → bold
    text = re.sub(r'^(#{1,4})\s+(.+)$', lambda m: bold(m.group(2)), text, flags=re.MULTILINE)
    return text


def _visible_len(text: str) -> int:
    """Return the visible length of a string, ignoring ANSI escape codes."""
    return len(_ANSI_STRIP_RE.sub("", text))


def _build_system_context(repo: str, agent_name: str) -> str:
    """Build the system context message for an agent, including bash tool and rules."""
    from .rules_loader import load_rules as _load_rules

    repo_name = os.path.basename(repo)
    rules_text = _load_rules(agent_name, repo)

    context = (
        f"IMPORTANT: You are working on the project at: {repo}\n"
        f"Project name: {repo_name}\n"
        f"This is the user's repository — all your analysis, code reading, "
        f"file operations, and responses must be about THIS project's files. "
        f"Do NOT describe the code-agents tool itself.\n"
        f"When reading files, searching code, or explaining architecture — "
        f"always operate within {repo}.\n"
        f"\n"
        f"--- Bash Tool ---\n"
        f"CRITICAL: You CANNOT make HTTP requests or network calls directly from your environment.\n"
        f"The ONLY way to execute commands is by outputting them in ```bash code blocks.\n"
        f"Commands run on the USER'S MACHINE (which has localhost and network access).\n"
        f"The output is automatically sent back to you so you can continue.\n"
        f"\n"
        f"HOW TO USE (follow this pattern exactly):\n"
        f"  1. Explain what you're about to do in 1 sentence\n"
        f"  2. Output exactly ONE command in a ```bash block\n"
        f"  3. STOP and wait — the command will run and output comes back to you\n"
        f"  4. Analyze the result, then propose the next command if needed\n"
        f"\n"
        f"RULES:\n"
        f"  - Output only ONE ```bash block at a time — never multiple in one response\n"
        f"  - The user will be asked 'Run this? [y/N]' — like Claude Code's CLI\n"
        f"  - After approval, output is fed back to you automatically\n"
        f"  - NEVER say 'I cannot reach the server' — output the curl and it will work\n"
        f"  - NEVER try to call APIs directly — always use ```bash blocks\n"
        f"\n"
        f"EXAMPLE:\n"
        f"  'Let me check the available Jenkins jobs.'\n"
        f"  ```bash\n"
        f"  curl -s http://127.0.0.1:8000/jenkins/jobs?folder=pg2/pg2-dev-build-jobs\n"
        f"  ```\n"
        f"  (wait for result, then continue)\n"
        f"--- End Bash Tool ---"
    )
    if rules_text:
        context += f"\n\n--- Rules ---\n{rules_text}\n--- End Rules ---"

    return context


def _print_welcome(agent_name: str) -> None:
    """Print agent welcome message in a red bordered box."""
    import shutil

    welcome = AGENT_WELCOME.get(agent_name)
    if not welcome:
        return

    title, capabilities, examples = welcome
    term_width = shutil.get_terminal_size((80, 24)).columns
    box_width = min(term_width - 4, 80)
    inner = box_width - 2

    def _pad(text: str) -> str:
        vis = _visible_len(text)
        pad = max(0, inner - vis - 1)
        return red("  │") + f" {text}{' ' * pad}" + red("│")

    print(red(f"  ┌{'─' * box_width}┐"))
    title_styled = f" {bold(cyan(title))}"
    title_pad = max(0, inner - len(title) - 1)
    print(red(f"  │") + title_styled + " " * title_pad + red("│"))
    print(red(f"  ├{'─' * box_width}┤"))
    print(_pad(""))
    print(_pad(bold("What I can do:")))
    for cap in capabilities:
        print(_pad(f"  • {cap}"))
    print(_pad(""))
    print(_pad(bold("Try asking:")))
    for ex in examples:
        print(_pad(f"  {dim(ex)}"))
    print(_pad(""))
    print(red(f"  └{'─' * box_width}┘"))
    print()


# ---------------------------------------------------------------------------
# Server communication
# ---------------------------------------------------------------------------


def _server_url() -> str:
    host = os.getenv("HOST", "127.0.0.1")
    port = os.getenv("PORT", "8000")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def _check_server(url: str) -> bool:
    """Check if the server is running."""
    import httpx
    try:
        r = httpx.get(f"{url}/health", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def _check_workspace_trust(repo_path: str) -> bool:
    """
    Check and auto-trust cursor-agent workspace for the target repo.

    If the workspace is not trusted, automatically trusts it using
    cursor-agent --trust --print. Returns True if trust is OK.
    """
    import shutil
    import subprocess

    # Skip if using HTTP mode or cursor-agent not installed
    if os.getenv("CURSOR_API_URL", "").strip():
        return True
    cli_path = shutil.which("cursor-agent")
    if not cli_path:
        return True

    # Quick check: does the workspace need trust?
    try:
        result = subprocess.run(
            [cli_path, "--print", "--output-format", "stream-json", "agent", "-"],
            cwd=repo_path,
            input="hi",
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return True

    if "Workspace Trust Required" not in (result.stderr or ""):
        return True  # Already trusted

    # Auto-trust using --trust flag
    print(dim(f"  Trusting workspace: {repo_path}"))
    try:
        trust_result = subprocess.run(
            [cli_path, "--trust", "--print", "--output-format", "stream-json", "agent", "-"],
            cwd=repo_path,
            input="hi",
            capture_output=True,
            text=True,
            timeout=15,
        )
        if "Workspace Trust Required" not in (trust_result.stderr or ""):
            print(green(f"  ✓ Workspace trusted for cursor-agent"))
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Auto-trust failed — show manual instructions
    print()
    print(yellow("  ⚠ Could not auto-trust workspace for cursor-agent"))
    print()
    print(f"    Directory: {bold(repo_path)}")
    print()
    print(f"    {bold('Fix manually (pick one):')}")
    print()
    print(f"    {cyan('Option 1:')} Trust interactively:")
    print(f"    {dim(f'  cd {repo_path} && cursor-agent agent')}")
    print(f"    {dim('  (type y to trust, then Ctrl+C to exit)')}")
    print()
    print(f"    {cyan('Option 2:')} Use HTTP mode (no CLI needed):")
    print(f"    {dim('  Set CURSOR_API_URL in your .env file')}")
    print()
    print(f"    {cyan('Option 3:')} Use a Claude backend agent:")
    print(f"    {dim('  Set ANTHROPIC_API_KEY in .env')}")
    print()
    return False


def _get_agents(url: str) -> dict[str, str]:
    """Fetch agent list from server. Returns {name: display_name}."""
    import httpx
    try:
        r = httpx.get(f"{url}/v1/agents", timeout=5.0)
        data = r.json()
        # Server may return {"data": [...]}, {"agents": [...]}, or a plain list
        if isinstance(data, dict):
            agents = data.get("data") or data.get("agents") or []
        elif isinstance(data, list):
            agents = data
        else:
            agents = []
        return {a.get("name", "?"): a.get("display_name", "") for a in agents if isinstance(a, dict)}
    except Exception:
        return {}


def _stream_chat(
    url: str,
    agent: str,
    messages: list[dict],
    session_id: Optional[str] = None,
    cwd: Optional[str] = None,
):
    """
    Send a chat request with streaming and yield response pieces.

    Yields tuples: (type, content) where type is "text", "reasoning", "session_id", or "error".
    """
    import httpx

    body: dict = {
        "messages": messages,
        "stream": True,
        "include_session": True,
        "stream_tool_activity": True,
    }
    if session_id:
        body["session_id"] = session_id
    if cwd:
        body["cwd"] = cwd

    endpoint = f"{url}/v1/agents/{agent}/chat/completions"

    try:
        with httpx.stream(
            "POST", endpoint,
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=300.0,
        ) as response:
            if response.status_code != 200:
                yield ("error", f"Server returned HTTP {response.status_code}")
                return

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]  # Strip "data: "
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # Extract session_id from final chunk
                if "session_id" in chunk:
                    yield ("session_id", chunk["session_id"])

                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})

                content = delta.get("content", "")
                if content:
                    yield ("text", content)

                reasoning = delta.get("reasoning_content", "")
                if reasoning:
                    yield ("reasoning", reasoning)

    except httpx.ConnectError:
        yield ("error", "Cannot connect to server. Is it running? (code-agents start)")
    except httpx.ReadTimeout:
        yield ("error", "Request timed out (300s). The agent may be processing a large task.")
    except Exception as e:
        yield ("error", str(e))


# ---------------------------------------------------------------------------
# Command extraction and execution
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(
    r"```(?:bash|sh|shell|zsh|console)\s*\n(.*?)```",
    re.DOTALL,
)


def _extract_commands(text: str) -> list[str]:
    """Extract shell commands from markdown code blocks in agent response.

    Handles multi-line commands joined with backslash continuations, e.g.:
        curl -X POST "http://..." \
          -H "Content-Type: application/json" \
          -d '{"query": "SELECT ..."}'
    """
    commands = []
    for match in _CODE_BLOCK_RE.finditer(text):
        block = match.group(1).strip()
        # Join backslash-continued lines first
        lines = block.splitlines()
        joined_lines: list[str] = []
        current = ""
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                # Flush any accumulated continuation before skipping
                if current:
                    joined_lines.append(current)
                    current = ""
                continue
            if current:
                # Continuing from previous line
                current += " " + stripped
            else:
                # Strip leading $ or > prompt markers
                if stripped.startswith("$ "):
                    stripped = stripped[2:]
                elif stripped.startswith("> "):
                    stripped = stripped[2:]
                current = stripped

            # Check if this line continues (ends with \)
            if current.endswith("\\"):
                current = current[:-1].rstrip()  # remove trailing \ and whitespace
            else:
                joined_lines.append(current)
                current = ""

        # Flush any remaining
        if current:
            joined_lines.append(current)

        for cmd in joined_lines:
            if cmd:
                commands.append(cmd)
    return commands


# Matches <UPPER_CASE> and {lower_case} placeholders
_PLACEHOLDER_ANGLE_RE = re.compile(r"<([A-Z][A-Z0-9_]+)>")
_PLACEHOLDER_CURLY_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def _resolve_placeholders(cmd: str) -> Optional[str]:
    """
    Detect placeholder tokens in a command and prompt user to fill them.

    Supports two styles:
      <DATA_SOURCE_ID>  — angle bracket, UPPER_CASE
      {job_name}        — curly brace, lower_case

    Returns the resolved command, or None if user cancels.
    """
    # Collect both styles: (placeholder_text, display_name)
    found: list[tuple[str, str]] = []
    for m in _PLACEHOLDER_ANGLE_RE.finditer(cmd):
        found.append((m.group(0), m.group(1)))  # ("<DATA_SOURCE_ID>", "DATA_SOURCE_ID")
    for m in _PLACEHOLDER_CURLY_RE.finditer(cmd):
        found.append((m.group(0), m.group(1)))  # ("{job_name}", "job_name")

    if not found:
        return cmd

    # Deduplicate while preserving order
    seen = set()
    unique: list[tuple[str, str]] = []
    for token, name in found:
        if token not in seen:
            seen.add(token)
            unique.append((token, name))

    print(f"    {yellow('Placeholders detected — fill in values:')}")
    replacements = {}
    for token, name in unique:
        try:
            value = input(f"    {bold(token)}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not value:
            print(dim(f"    Skipped (no value for {token})."))
            return None
        replacements[token] = value

    for token, value in replacements.items():
        cmd = cmd.replace(token, value)

    return cmd


def _offer_run_commands(
    commands: list[str], cwd: str,
    agent_name: str = "",
) -> list[dict[str, str]]:
    """
    Offer to run detected shell commands one at a time.

    - If command is already saved in agent's project rules → auto-run (no prompt)
    - If not trusted → ask 1. Yes / 2. No → if approved, auto-save to rules
    - Saved commands are per-agent, per-repo (in .code-agents/rules/{agent}.md)

    Returns list of executed results for the agentic feedback loop.
    """
    results: list[dict[str, str]] = []

    if not commands:
        return results

    for cmd in commands:
        import shutil
        import textwrap
        term_width = shutil.get_terminal_size((80, 24)).columns
        box_width = min(term_width - 4, 100)
        inner = box_width - 2

        # Check if this command is already trusted (saved in rules)
        trusted = _is_command_trusted(cmd, agent_name, cwd) if agent_name else False

        # Show the command in a box
        print(red(f"  ┌{'─' * box_width}┐"))
        cmd_lines = textwrap.wrap(cmd, width=inner - 3)
        for idx, line in enumerate(cmd_lines):
            if idx == 0:
                prefix = f" {bold('$')} {cyan(line)}"
                vis_len = len(f" $ {line}")
            else:
                prefix = f"   {cyan(line)}"
                vis_len = len(f"   {line}")
            pad = max(0, inner - vis_len)
            print(red(f"  │") + prefix + " " * pad + red("│"))
        print(red(f"  └{'─' * box_width}┘"))

        save_after = False
        if trusted:
            # Auto-approved — command is in the agent's rules
            from .rules_loader import PROJECT_RULES_DIRNAME
            rules_path = os.path.join(cwd, PROJECT_RULES_DIRNAME, f"{agent_name}.md") if agent_name else ""
            print(f"  {green('● Auto-approved')} {dim(f'(saved in {rules_path})')}")
        else:
            # Build the save path for display
            from .rules_loader import PROJECT_RULES_DIRNAME
            if agent_name and cwd:
                save_path = os.path.join(cwd, PROJECT_RULES_DIRNAME, f"{agent_name}.md")
                save_display = dim(f"→ {save_path}")
            else:
                save_display = ""

            # 3-option approval: Yes, Yes & Save, No
            print(f"  {bold('Run this command?')}")
            print(f"    {bold('1.')} Yes")
            print(f"    {bold('2.')} Yes & Save to {cyan(agent_name or 'agent')} rules {save_display}")
            print(f"    {bold('3.')} No")
            try:
                choice = input(f"  {dim('Choose [1/2/3]')}: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return results

            if choice in ("3", "n", "no"):
                print(dim("  Skipped."))
                print()
                continue
            elif choice in ("", "1", "y", "yes"):
                save_after = False
            elif choice == "2":
                save_after = True
            else:
                save_after = False  # default: run but don't save

        # Resolve placeholders if any
        resolved = _resolve_placeholders(cmd)
        if not resolved:
            continue

        # Run it
        output = _run_single_command(resolved, cwd)
        results.append({"command": resolved, "output": output})

        # Save to rules if user chose option 2
        if save_after and agent_name and cwd:
            _save_command_to_rules(resolved, agent_name, cwd)

    return results


def _run_single_command(cmd: str, cwd: str) -> str:
    """Run a single shell command, display in red box, and return raw output."""
    import subprocess
    import shutil

    # Green BASH indicator
    print(f"  {bold(green('● BASH'))} {dim('running...')}")

    term_width = shutil.get_terminal_size((80, 24)).columns
    box_width = min(term_width - 4, 100)
    inner_width = box_width - 2

    def _box_line(text: str) -> str:
        visible = text[:inner_width]
        pad = max(0, inner_width - len(visible))
        return red(f"  │") + f" {visible}{' ' * pad}" + red("│")

    # Top border + command (wrapped across multiple lines)
    import textwrap
    print(red(f"  ┌{'─' * box_width}┐"))
    cmd_lines = textwrap.wrap(cmd, width=inner_width - 3)
    for idx, line in enumerate(cmd_lines):
        if idx == 0:
            prefix = f" {bold('$')} {cyan(line)}"
            vis_len = len(f" $ {line}")
        else:
            prefix = f"   {cyan(line)}"
            vis_len = len(f"   {line}")
        pad = max(0, inner_width - vis_len)
        print(red(f"  │") + prefix + " " * pad + red("│"))
    print(red(f"  ├{'─' * box_width}┤"))

    raw_output = ""
    try:
        import time as _cmd_time
        import threading

        # Run command with live timer (no hard timeout — poll instead)
        proc = subprocess.Popen(
            cmd, shell=True, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        # Show live elapsed timer + poll Jenkins status after 120s
        _cmd_start = _cmd_time.monotonic()
        _cmd_done = threading.Event()
        _is_jenkins = "jenkins" in cmd.lower() and ("build" in cmd.lower() or "wait" in cmd.lower())

        def _poll_jenkins_status() -> str:
            """Try to fetch Jenkins build status from the local API."""
            try:
                import httpx
                # Try to get the last build status for any jenkins job
                r = httpx.get("http://127.0.0.1:8000/health", timeout=2.0)
                if r.status_code != 200:
                    return ""
                # Try last build for the configured job
                build_job = os.getenv("JENKINS_BUILD_JOB", "")
                if build_job:
                    r = httpx.get(f"http://127.0.0.1:8000/jenkins/build/{build_job}/last", timeout=5.0)
                    if r.status_code == 200:
                        data = r.json()
                        building = data.get("building", False)
                        result = data.get("result") or ("BUILDING" if building else "UNKNOWN")
                        num = data.get("number", "?")
                        return f"Build #{num}: {result}"
            except Exception:
                pass
            return ""

        def _show_cmd_timer():
            _last_status = ""
            while not _cmd_done.is_set():
                elapsed = _cmd_time.monotonic() - _cmd_start
                if elapsed < 60:
                    t = f"{elapsed:.0f}s"
                else:
                    m, s = divmod(int(elapsed), 60)
                    t = f"{m}m {s:02d}s"

                # After 120s, poll Jenkins status every 15s
                status_str = ""
                if _is_jenkins and elapsed > 120 and int(elapsed) % 15 == 0:
                    polled = _poll_jenkins_status()
                    if polled:
                        _last_status = polled
                if _last_status:
                    status_str = f" — {_last_status}"

                line = f"\r  {yellow('⏱')} {dim(f'Running... {t}{status_str}')}"
                sys.stdout.write(f"{line}{' ' * 10}")
                sys.stdout.flush()
                _cmd_done.wait(1)
            sys.stdout.write(f"\r{' ' * 80}\r")
            sys.stdout.flush()

        timer_thread = threading.Thread(target=_show_cmd_timer, daemon=True)
        timer_thread.start()

        stdout_data, stderr_data = proc.communicate(timeout=600)
        _cmd_done.set()
        timer_thread.join(timeout=1)

        elapsed = _cmd_time.monotonic() - _cmd_start
        result_stdout = stdout_data.decode("utf-8", errors="replace") if stdout_data else ""
        result_stderr = stderr_data.decode("utf-8", errors="replace") if stderr_data else ""
        raw_output = result_stdout + result_stderr

        display_lines = []
        if result_stdout:
            stdout = result_stdout
            try:
                import json as _json
                parsed = _json.loads(stdout)
                stdout = _json.dumps(parsed, indent=2, ensure_ascii=False)
            except (ValueError, TypeError):
                pass
            display_lines.extend(stdout.splitlines())
        if result_stderr:
            display_lines.extend(result_stderr.splitlines())

        if display_lines:
            for line in display_lines:
                print(_box_line(line))

            # Copy full output to clipboard (macOS pbcopy)
            if result_stdout:
                try:
                    subprocess.run(
                        ["pbcopy"], input=result_stdout.encode(),
                        capture_output=True, timeout=2,
                    )
                    print(_box_line(dim("(copied to clipboard)")))
                except Exception:
                    pass

        # Show elapsed time in status
        if elapsed < 60:
            time_str = f"{elapsed:.1f}s"
        else:
            m, s = divmod(int(elapsed), 60)
            time_str = f"{m}m {s:02d}s"

        if proc.returncode != 0:
            status_text = f" ✗ Exit code: {proc.returncode} ({time_str})"
            pad = max(0, inner_width - len(status_text))
            print(red(f"  │ {status_text}") + " " * pad + red("│"))
            raw_output += f"\n[exit code: {proc.returncode}]"
        else:
            status_text = f" ✓ Done ({time_str})"
            pad = max(0, inner_width - len(status_text))
            print(red("  │") + green(status_text) + " " * pad + red("│"))

    except subprocess.TimeoutExpired:
        _cmd_done.set()
        timer_thread.join(timeout=1)
        proc.kill()
        stdout_data, stderr_data = proc.communicate()
        raw_output = (stdout_data or b"").decode("utf-8", errors="replace")
        print(_box_line(yellow("Command still running after 10 minutes")))
        print(_box_line(dim("Partial output captured. Check server logs for status.")))
        if raw_output:
            for line in raw_output.splitlines()[-10:]:
                print(_box_line(line))
    except Exception as e:
        print(_box_line(red(f"Error: {e}")))
        raw_output = f"[error: {e}]"

    print(red(f"  └{'─' * box_width}┘"))
    print()
    return raw_output


# ---------------------------------------------------------------------------
# Slash command handlers
# ---------------------------------------------------------------------------


def _make_completer(
    slash_commands: list[str], agent_names: list[str]
) -> callable:
    """
    Build a readline completer for slash commands and agent names.

    Completes:
    - First token starting with / → slash commands + /agent-name
    - Second token after '/agent ' → bare agent names

    Returns a function suitable for readline.set_completer().
    """
    agent_completions = [f"/{name}" for name in agent_names]
    all_completions = slash_commands + agent_completions

    def completer(text: str, idx: int) -> Optional[str]:
        try:
            import readline
            line = readline.get_line_buffer().lstrip()
        except (ImportError, AttributeError):
            line = text

        # Second word after '/agent ' → complete bare agent names
        if line.startswith("/agent ") and not text.startswith("/"):
            matches = [n for n in agent_names if n.startswith(text)]
            return matches[idx] if idx < len(matches) else None

        # First token starting with /
        if text.startswith("/"):
            matches = [c for c in all_completions if c.startswith(text)]
            return matches[idx] if idx < len(matches) else None

        return None

    return completer


def _parse_inline_delegation(
    user_input: str, available_agents: dict[str, str]
) -> tuple[Optional[str], Optional[str]]:
    """
    Parse a slash command to see if it's an inline agent delegation.

    Returns (agent_name, prompt) if it matches, or (None, None) otherwise.
    A bare agent name with no prompt returns (agent_name, "") for permanent switch.
    """
    if not user_input.startswith("/"):
        return None, None
    parts = user_input.split(None, 1)
    slash_cmd = parts[0][1:]  # strip leading /
    slash_arg = parts[1] if len(parts) > 1 else ""

    if slash_cmd in available_agents:
        return slash_cmd, slash_arg
    return None, None


def _handle_command(cmd: str, state: dict, url: str) -> Optional[str]:
    """
    Handle a slash command. Returns None to continue, or "quit" to exit.
    Modifies state dict in-place.
    """
    parts = cmd.strip().rstrip(";").strip().split(None, 1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command in ("/quit", "/exit", "/q", "/bye"):
        return "quit"

    elif command == "/restart":
        import subprocess as _sp
        port = os.getenv("PORT", "8000")
        print()
        print(bold(cyan("  Restarting server...")))
        # Kill existing
        try:
            result = _sp.run(["lsof", f"-ti:{port}"], capture_output=True, text=True)
            pids = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
            if pids:
                for pid in pids:
                    os.kill(int(pid), 15)
                import time
                time.sleep(1)
                # Force kill stragglers
                check = _sp.run(["lsof", f"-ti:{port}"], capture_output=True, text=True)
                for pid in [p.strip() for p in check.stdout.strip().splitlines() if p.strip()]:
                    os.kill(int(pid), 9)
                print(green(f"  ✓ Server stopped"))
        except Exception:
            pass
        # Start new
        cwd = state.get("repo_path", os.getcwd())
        code_agents_home = str(Path(__file__).resolve().parent.parent)
        env = os.environ.copy()
        env["TARGET_REPO_PATH"] = cwd
        log_dir = Path(code_agents_home) / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "code-agents.log"
        _sp.Popen(
            [sys.executable, "-m", "code_agents.main"],
            cwd=code_agents_home,
            env=env,
            stdout=_sp.DEVNULL,
            stderr=open(str(log_file), "a"),
        )
        import time
        for _ in range(10):
            time.sleep(1)
            if _check_server(_server_url()):
                print(green(f"  ✓ Server restarted at {_server_url()}"))
                break
        else:
            print(red(f"  ✗ Server failed to restart. Check: code-agents logs"))
        print()

    elif command == "/run":
        # Manual run: /run <command> — run only, no agent feedback
        if not arg:
            print(yellow("  Usage: /run <shell command>"))
            return None
        _run_single_command(arg, state.get("repo_path", "."))
        return None

    elif command == "/execute" or command == "/exec":
        # Execute + feed output to agent: /execute <command>
        if not arg:
            print(yellow("  Usage: /execute <shell command>"))
            print(dim("  Runs the command and sends output to the agent for analysis."))
            return None
        resolved = _resolve_placeholders(arg)
        if not resolved:
            return None
        output = _run_single_command(resolved, state.get("repo_path", "."))
        # Return special signal for REPL to feed back to agent
        state["_exec_feedback"] = {
            "command": resolved,
            "output": output,
        }
        return "exec_feedback"

    elif command == "/help":
        print()
        print(bold("  Chat Commands:"))
        print(f"    {cyan('/quit'):<16} Exit chat")
        print(f"    {cyan('/agent <name>'):<16} Switch to another agent permanently")
        print(f"    {cyan('/agents'):<16} List all available agents")
        print(f"    {cyan('/run <cmd>'):<16} Run a shell command in the repo directory")
        print(f"    {cyan('/exec <cmd>'):<16} Run command and send output to agent for analysis")
        print(f"    {cyan('/open'):<16} View last response in pager (less/editor)")
        print(f"    {cyan('/restart'):<16} Restart the server")
        print(f"    {cyan('/rules'):<16} Show active rules for current agent")
        print(f"    {cyan('/session'):<16} Show current session ID")
        print(f"    {cyan('/history'):<16} List previous chat sessions")
        print(f"    {cyan('/resume <id>'):<16} Resume a chat by session ID")
        print(f"    {cyan('/delete-chat <id>'):<16} Delete a chat by session ID")
        print(f"    {cyan('/clear'):<16} Clear session (fresh start, same agent)")
        print(f"    {cyan('/help'):<16} Show this help")
        print()
        print(bold("  Inline agent delegation:"))
        print(f"    {cyan('/<agent> <prompt>'):<16}")
        print(f"    Send a one-shot prompt to another agent without switching.")
        print(f"    Your current agent stays active after the response.")
        print()
        print(bold("  Command execution:"))
        print(f"    When an agent suggests shell commands (in ```bash blocks),")
        print(f"    you'll be prompted to run them: {cyan('[y/N/all/skip]')}")
        print()
        print(f"    {dim('Example:')}")
        print(f"    {dim('/code-reviewer Review the auth module for security issues')}")
        print(f"    {dim('/code-writer Add input validation to the login function')}")
        print(f"    {dim('/run git status')}")
        print()

    elif command == "/agents":
        agents = _get_agents(url)
        current = state.get("agent", "")
        print()
        print(bold("  Available agents:"))
        for name, display in sorted(agents.items()):
            marker = f" {green('← current')}" if name == current else ""
            role = AGENT_ROLES.get(name, "")
            print(f"    {cyan(name):<28} {dim(role)}{marker}")
        print()
        print(dim(f"  Switch: /agent <name>"))
        print()

    elif command == "/agent":
        if not arg:
            print(yellow("  Usage: /agent <name>  (e.g. /agent code-writer)"))
            return None
        agents = _get_agents(url)
        if arg not in agents:
            print(red(f"  Agent '{arg}' not found."))
            print(dim(f"  Available: {', '.join(sorted(agents.keys()))}"))
            return None
        state["agent"] = arg
        state["session_id"] = None
        role = AGENT_ROLES.get(arg, agents.get(arg, ""))
        print()
        print(green(f"  ✓ Switched to: {bold(arg)} ({agents.get(arg, '')})"))
        print(f"    Session: {dim('new')}")
        print()
        _print_welcome(arg)

    elif command == "/session":
        sid = state.get("session_id")
        if sid:
            print(f"  Session: {cyan(sid)}")
        else:
            print(dim("  No active session (will be created on first message)"))

    elif command == "/clear":
        state["session_id"] = None
        state["_chat_session"] = None
        print(green("  ✓ Session cleared. Next message starts fresh."))

    elif command == "/open":
        # Open last output in pager or editor
        last_output = state.get("_last_output", "")
        if not last_output:
            print(dim("  No output to view."))
            return None
        import tempfile
        import subprocess as _sp
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, prefix="code-agents-") as f:
            f.write(last_output)
            tmp_path = f.name
        pager = os.environ.get("PAGER", "less -R")
        try:
            _sp.run(pager.split() + [tmp_path])
        except FileNotFoundError:
            # Fallback: try open on macOS
            try:
                _sp.run(["open", tmp_path])
            except FileNotFoundError:
                print(f"  {dim(f'Saved to: {tmp_path}')}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    elif command == "/history":
        from .chat_history import list_sessions as _list_sessions
        repo = state.get("repo_path")
        show_all = arg == "--all"
        sessions = _list_sessions(limit=15, repo_path=None if show_all else repo)
        print()
        if not sessions:
            print(dim("  No chat history found."))
        else:
            print(bold("  Recent chats:"))
            print()
            for i, s in enumerate(sessions, 1):
                ts = datetime.fromtimestamp(s["updated_at"]).strftime("%b %d %H:%M")
                agent_label = cyan(s["agent"])
                msg_count = s["message_count"]
                title = s["title"]
                repo_name = os.path.basename(s.get("repo_path", ""))
                sid = s["id"]
                print(f"    {cyan(sid)}")
                print(f"      {title}")
                print(f"      {agent_label}  {dim(f'{msg_count} msgs')}  {dim(ts)}  {dim(repo_name)}")
            print()
            print(dim("  Use /resume <session-id> to continue a chat"))
            if not show_all:
                print(dim("  Use /history --all to show chats from all repos"))
        print()

    elif command == "/resume":
        if not arg:
            print(yellow("  Usage: /resume <session-id>  (from /history list)"))
            return None
        from .chat_history import load_session as _load_sess
        loaded = _load_sess(arg.strip())
        if loaded:
            state["agent"] = loaded["agent"]
            state["session_id"] = loaded.get("_server_session_id")
            state["_chat_session"] = loaded
            print()
            print(green(f"  \u2713 Resumed: {bold(loaded['title'])}"))
            print(f"    Agent: {cyan(loaded['agent'])}  Messages: {len(loaded['messages'])}")
            recent = loaded["messages"][-4:]
            if recent:
                print()
                print(dim("  Recent context:"))
                for msg in recent:
                    role_label = green("you") if msg["role"] == "user" else magenta(loaded["agent"])
                    preview = msg["content"][:100]
                    if len(msg["content"]) > 100:
                        preview += "..."
                    print(f"    {bold(role_label)} \u203a {dim(preview)}")
            print()
        else:
            print(red(f"  Session '{arg}' not found. Use /history to list sessions."))
    elif command == "/delete-chat":
        if not arg:
            print(yellow("  Usage: /delete-chat <session-id>  (from /history list)"))
            return None
        from .chat_history import delete_session as _del
        if _del(arg.strip()):
            print(green(f"  ✓ Deleted session: {arg.strip()}"))
        else:
            print(red(f"  Session '{arg}' not found. Use /history to list sessions."))

    elif command == "/rules":
        from .rules_loader import list_rules
        repo = state.get("repo_path", ".")
        agent = state.get("agent", "")
        rules = list_rules(agent_name=agent, repo_path=repo)
        print()
        if not rules:
            print(dim(f"  No rules active for {bold(agent)}."))
            print(dim(f"  Create one: code-agents rules create --agent {agent}"))
        else:
            print(bold(f"  Rules for {cyan(agent)}:"))
            for r in rules:
                scope_label = green("global") if r["scope"] == "global" else cyan("project")
                target_label = "all agents" if r["target"] == "_global" else r["target"]
                print(f"    [{scope_label}] {bold(target_label)}")
                print(f"      {dim(r['preview'])}")
                print(f"      {dim(r['path'])}")
        print()

    else:
        print(yellow(f"  Unknown command: {command}"))
        print(dim("  Type /help for available commands"))

    return None


# ---------------------------------------------------------------------------
# Main chat loop
# ---------------------------------------------------------------------------


def _select_agent(agents: dict[str, str]) -> Optional[str]:
    """Interactive agent selection menu. Returns agent name or None to cancel."""
    sorted_agents = sorted(agents.items())

    print()
    print(bold("  Select an agent:"))
    print()
    for i, (name, display) in enumerate(sorted_agents, 1):
        role = AGENT_ROLES.get(name, display)
        print(f"    {bold(str(i) + '.'):<6} {cyan(name):<28} {dim(role)}")
    print()
    print(f"    {dim('0.')}    {dim('Cancel')}")
    print()

    while True:
        try:
            choice = input(f"  {bold('Pick agent')} [1-{len(sorted_agents)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not choice:
            continue
        if choice == "0":
            return None
        try:
            idx = int(choice)
            if 1 <= idx <= len(sorted_agents):
                return sorted_agents[idx - 1][0]
        except ValueError:
            # Allow typing the agent name directly
            if choice in agents:
                return choice
        print(red(f"    Enter a number 1-{len(sorted_agents)}, or an agent name."))


def chat_main(args: list[str] | None = None):
    """Entry point for the interactive chat REPL."""
    args = args or []

    # Load env — global config + per-repo overrides
    cwd = os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
    from .env_loader import load_all_env
    load_all_env(cwd)

    url = _server_url()

    # Check server — offer to start if not running
    if not _check_server(url):
        print()
        print(yellow(f"  Server is not running at {url}"))
        print()
        try:
            answer = input(f"  Start the server now? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer in ("", "y", "yes"):
            print(dim("  Starting server in background..."))
            # Import and start background
            import subprocess as _sp
            import time as _time
            code_agents_home = str(Path(__file__).resolve().parent.parent)
            env = os.environ.copy()
            env["TARGET_REPO_PATH"] = cwd
            log_dir = Path(code_agents_home) / "logs"
            log_dir.mkdir(exist_ok=True)
            log_file = log_dir / "code-agents.log"
            _sp.Popen(
                [sys.executable, "-m", "code_agents.main"],
                cwd=code_agents_home,
                env=env,
                stdout=_sp.DEVNULL,
                stderr=open(str(log_file), "a"),
            )
            # Wait for server to be ready
            for _ in range(10):
                _time.sleep(1)
                if _check_server(url):
                    print(green(f"  ✓ Server started at {url}"))
                    break
            else:
                print(red(f"  ✗ Server failed to start. Check: code-agents logs"))
                return
        else:
            print(f"  Start it with: {bold('code-agents start')}")
            return
        print()

    # Fetch agents from server
    agents = _get_agents(url)
    if not agents:
        print()
        print(red("  No agents loaded from server."))
        print(f"  Server is running at {url} but returned no agents.")
        print()
        print(bold("  Troubleshoot:"))
        print(f"    code-agents doctor                  {dim('# diagnose issues')}")
        print(f"    code-agents logs                    {dim('# check server logs')}")
        print(f"    curl -s {url}/v1/agents | python3 -m json.tool")
        print()
        return

    # Determine agent: from args or interactive selection
    agent_name = None
    for i, a in enumerate(args):
        if a == "--agent" and i + 1 < len(args):
            agent_name = args[i + 1]
            break
        elif not a.startswith("-"):
            agent_name = a
            break

    # Check for --resume flag
    _resume_id = None
    for i, a in enumerate(args):
        if a == "--resume" and i + 1 < len(args):
            _resume_id = args[i + 1]
            break

    if agent_name and agent_name not in agents:
        print(red(f"  Agent '{agent_name}' not found."))
        agent_name = None

    if not agent_name:
        # Show banner then agent selection
        print()
        print(bold(cyan("  ╔══════════════════════════════════════════════╗")))
        print(bold(cyan("  ║       Code Agents — Interactive Chat         ║")))
        print(bold(cyan("  ╚══════════════════════════════════════════════╝")))

        agent_name = _select_agent(agents)
        if not agent_name:
            print(dim("  Cancelled."))
            return

    # Detect repository — find the git root from cwd
    repo_path = cwd
    is_repo = False
    check_dir = cwd
    while True:
        if os.path.isdir(os.path.join(check_dir, ".git")):
            repo_path = check_dir
            is_repo = True
            break
        parent = os.path.dirname(check_dir)
        if parent == check_dir:
            break  # reached filesystem root
        check_dir = parent

    # Pre-flight: check cursor-agent workspace trust
    if not _check_workspace_trust(repo_path):
        return

    # State
    state = {
        "agent": agent_name,
        "session_id": None,
        "repo_path": repo_path,
        "_chat_session": None,
    }

    # Handle --resume flag: load a previous session by UUID
    if _resume_id:
        from .chat_history import load_session as _load_sess
        loaded = _load_sess(_resume_id.strip())
        if loaded:
            state["agent"] = loaded["agent"]
            state["session_id"] = loaded.get("_server_session_id")
            state["_chat_session"] = loaded
            agent_name = loaded["agent"]
            print()
            print(green(f"  ✓ Resumed: {bold(loaded['title'])}"))
            print(f"    Agent: {cyan(loaded['agent'])}  Messages: {len(loaded['messages'])}")
            recent = loaded["messages"][-4:]
            if recent:
                print()
                print(dim("  Recent context:"))
                for msg in recent:
                    role_label = green("you") if msg["role"] == "user" else magenta(loaded["agent"])
                    preview = msg["content"][:100]
                    if len(msg["content"]) > 100:
                        preview += "..."
                    print(f"    {bold(role_label)} › {dim(preview)}")
            print()
        else:
            print(red(f"  Session '{_resume_id}' not found."))
            print(dim("  Use 'code-agents sessions' to see session IDs."))
            return

    # Tab-completion for slash commands and agent names
    _slash_commands = ["/help", "/quit", "/exit", "/agents", "/agent", "/run", "/exec", "/execute", "/open", "/restart", "/rules", "/session", "/clear", "/history", "/resume", "/delete-chat"]
    _completer = _make_completer(_slash_commands, list(agents.keys()))
    _has_readline = False

    try:
        import readline
        readline.set_completer(_completer)
        readline.set_completer_delims(" \t")
        # macOS uses libedit which needs a different parse_and_bind syntax
        if "libedit" in (readline.__doc__ or ""):
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")
        _has_readline = True
    except ImportError:
        pass  # readline not available on some platforms

    # Banner
    display_name = agents.get(agent_name, agent_name)
    role = AGENT_ROLES.get(agent_name, "")

    print()
    print(bold(cyan("  ╔══════════════════════════════════════════════╗")))
    print(bold(cyan("  ║       Code Agents — Interactive Chat         ║")))
    print(bold(cyan("  ╚══════════════════════════════════════════════╝")))
    print()
    print(f"  Agent:   {bold(agent_name)} ({display_name})")
    print(f"  Role:    {dim(role)}")
    if is_repo:
        # Show repo name prominently
        repo_name = os.path.basename(repo_path)
        print(f"  Repo:    {bold(cyan(repo_name))} ({repo_path})")
        print(f"           {dim('Agent will work on this project')}")
    else:
        print(f"  Dir:     {yellow(cwd)}")
        print(f"           {yellow('No git repo detected — agent has no project context')}")
    print(f"  Server:  {dim(url)}")
    print()
    print(dim("  Commands: /help /quit /agents /agent <name> /history /resume /clear"))
    print()

    # Welcome message
    _print_welcome(agent_name)

    # REPL
    while True:
        try:
            # Read input (supports multi-line with \ continuation)
            lines = []
            prompt_str = f"  {_rl_bold(_rl_green('you'))} › " if _has_readline else f"  {bold(green('you'))} › "
            while True:
                line = input(prompt_str if not lines else "  ... ")
                if line.endswith("\\"):
                    lines.append(line[:-1])
                    continue
                lines.append(line)
                break
            user_input = "\n".join(lines).strip()

            if not user_input:
                continue

            # Auto-save: ensure a chat session exists and save user message
            if not state.get("_chat_session"):
                from .chat_history import create_session
                state["_chat_session"] = create_session(state["agent"], state["repo_path"])
            from .chat_history import add_message as _add_msg
            _add_msg(state["_chat_session"], "user", user_input)

            # Slash commands
            if user_input.startswith("/"):
                # Is this an agent name? e.g. /code-reasoning, /code-writer
                available_agents = _get_agents(url) if not hasattr(state, "_agents_cache") else state.get("_agents_cache", {})
                if not available_agents:
                    available_agents = _get_agents(url)
                state["_agents_cache"] = available_agents

                delegate_agent, delegate_prompt = _parse_inline_delegation(
                    user_input, available_agents
                )

                if delegate_agent and delegate_prompt:
                    # Inline delegation — send this prompt to that agent, then return to current
                    role = AGENT_ROLES.get(delegate_agent, "")
                    print(dim(f"\n  Delegating to {bold(cyan(delegate_agent))}: {dim(role)}"))

                    # Build messages with repo context + bash tool + rules
                    repo = state.get("repo_path", cwd)
                    system_context = _build_system_context(repo, delegate_agent)
                    delegate_messages = [
                        {"role": "system", "content": system_context},
                        {"role": "user", "content": delegate_prompt},
                    ]

                    agent_label = bold(magenta(delegate_agent))
                    sys.stdout.write(f"\n  {agent_label} › ")
                    sys.stdout.flush()

                    got_text = False
                    delegate_response: list[str] = []
                    for piece_type, piece_content in _stream_chat(
                        url, delegate_agent, delegate_messages, None,
                        cwd=state.get("repo_path"),
                    ):
                        if piece_type == "text":
                            got_text = True
                            delegate_response.append(piece_content)
                            sys.stdout.write(_render_markdown(piece_content))
                            sys.stdout.flush()
                        elif piece_type == "reasoning":
                            sys.stdout.write(f"\n    {dim(piece_content.strip())}")
                            sys.stdout.flush()
                        elif piece_type == "error":
                            print(red(f"\n  Error: {piece_content}"))

                    if got_text:
                        print()
                    print()

                    # Offer to run detected shell commands
                    if delegate_response:
                        cmds = _extract_commands("".join(delegate_response))
                        if cmds:
                            _offer_run_commands(cmds, state.get("repo_path", cwd), agent_name=delegate_agent)

                    # Back to current agent — no state change
                    current = state["agent"]
                    print(dim(f"  (back to {current})"))
                    print()
                    continue

                elif delegate_agent and not delegate_prompt:
                    # Just agent name with no prompt — switch permanently (same as /agent)
                    _handle_command(f"/agent {delegate_agent}", state, url)
                    continue

                # Regular slash command
                result = _handle_command(user_input, state, url)
                if result == "quit":
                    print()
                    print(dim("  Chat ended."))
                    print()
                    break
                elif result == "exec_feedback":
                    # /execute ran a command — feed output to agent
                    fb = state.pop("_exec_feedback", None)
                    if fb:
                        repo = state.get("repo_path", cwd)
                        current_agent = state["agent"]
                        system_context = _build_system_context(repo, current_agent)

                        output_preview = fb["output"][:3000] if fb["output"] else "(no output)"
                        feedback = (
                            f"I ran this command:\n{fb['command']}\n\n"
                            f"Output:\n{output_preview}\n\n"
                            f"Please analyze the output and suggest next steps."
                        )

                        print(dim("  Feeding output to agent..."))
                        print()

                        agent_label = bold(magenta(current_agent))
                        sys.stdout.write(f"  {agent_label} › ")
                        sys.stdout.flush()

                        for piece_type, piece_content in _stream_chat(
                            url, current_agent,
                            [{"role": "system", "content": system_context},
                             {"role": "user", "content": feedback}],
                            state.get("session_id"),
                            cwd=state.get("repo_path"),
                        ):
                            if piece_type == "text":
                                sys.stdout.write(_render_markdown(piece_content))
                                sys.stdout.flush()
                            elif piece_type == "reasoning":
                                sys.stdout.write(f"\n    {dim(piece_content.strip())}")
                                sys.stdout.flush()
                            elif piece_type == "session_id":
                                state["session_id"] = piece_content
                            elif piece_type == "error":
                                print(red(f"\n  Error: {piece_content}"))

                        print()
                        print()
                continue

            # Build messages — inject repo context + bash tool + rules
            repo = state.get("repo_path", cwd)
            current_agent = state["agent"]
            system_context = _build_system_context(repo, current_agent)

            # Send full conversation history (like Claude CLI)
            messages = [{"role": "system", "content": system_context}]
            chat_session = state.get("_chat_session")
            if chat_session and chat_session.get("messages"):
                for hist_msg in chat_session["messages"]:
                    # Skip current message (already being added below)
                    if hist_msg.get("role") in ("user", "assistant"):
                        messages.append({"role": hist_msg["role"], "content": hist_msg["content"]})
            # Only add current user_input if not already the last message in history
            if not messages or messages[-1].get("content") != user_input:
                messages.append({"role": "user", "content": user_input})

            # Stream response with spinner + live timer
            current_agent = state["agent"]
            agent_label = bold(magenta(current_agent))
            import threading
            import itertools
            import time as _time
            _response_start = _time.monotonic()
            _stop_spin = threading.Event()

            def _format_elapsed(seconds: float) -> str:
                if seconds < 60:
                    return f"{seconds:.0f}s"
                m, s = divmod(int(seconds), 60)
                return f"{m}m {s:02d}s"

            def _show_spinner():
                frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                for frame in itertools.cycle(frames):
                    if _stop_spin.is_set():
                        break
                    elapsed = _time.monotonic() - _response_start
                    sys.stdout.write(f"\r  {yellow(frame)} {dim(f'Thinking... {_format_elapsed(elapsed)}')}")
                    sys.stdout.flush()
                    _stop_spin.wait(0.1)
                sys.stdout.write(f"\r{' ' * 40}\r")
                sys.stdout.flush()

            spin_thread = threading.Thread(target=_show_spinner, daemon=True)
            spin_thread.start()

            got_text = False
            full_response: list[str] = []
            for piece_type, piece_content in _stream_chat(
                url, current_agent, messages, state.get("session_id"),
                cwd=state.get("repo_path"),
            ):
                if piece_type == "text":
                    if not got_text:
                        # Stop spinner, show agent label
                        _stop_spin.set()
                        spin_thread.join(timeout=1)
                        sys.stdout.write(f"  {agent_label} › ")
                        sys.stdout.flush()
                    got_text = True
                    full_response.append(piece_content)
                    sys.stdout.write(_render_markdown(piece_content))
                    sys.stdout.flush()

                elif piece_type == "reasoning":
                    # Stop spinner if still running
                    if not _stop_spin.is_set():
                        _stop_spin.set()
                        spin_thread.join(timeout=1)
                    # Show tool activity in dimmed style
                    sys.stdout.write(f"\n    {dim(piece_content.strip())}")
                    sys.stdout.flush()

                elif piece_type == "session_id":
                    state["session_id"] = piece_content

                elif piece_type == "error":
                    if not _stop_spin.is_set():
                        _stop_spin.set()
                        spin_thread.join(timeout=1)
                    print(red(f"\n  Error: {piece_content}"))

            # Ensure spinner is stopped
            if not _stop_spin.is_set():
                _stop_spin.set()
                spin_thread.join(timeout=1)

            if got_text:
                print()  # Newline after response

            # Save last response
            full_text = "".join(full_response) if full_response else ""
            state["_last_output"] = full_text

            # Auto-save agent response to chat history
            if full_text and state.get("_chat_session"):
                from .chat_history import add_message as _save_msg
                _save_msg(state["_chat_session"], "assistant", full_text)
                # Persist server session_id for potential resume
                if state.get("session_id"):
                    state["_chat_session"]["_server_session_id"] = state["session_id"]
                    from .chat_history import _save as _persist
                    _persist(state["_chat_session"])

            # Auto-collapse long responses (like Claude Code) with Ctrl+O toggle
            response_lines = full_text.splitlines()
            if len(response_lines) > 25:
                # Clear the streamed output and show collapsed view
                lines_to_clear = len(response_lines) + 2
                for _ in range(lines_to_clear):
                    sys.stdout.write(f"\033[A\033[2K")
                sys.stdout.flush()

                _is_expanded = False

                def _show_collapsed():
                    print(f"  {agent_label} › ", end="")
                    for line in response_lines[:8]:
                        print(f"  {_render_markdown(line)}")
                    print(f"  {dim(f'  ... ({len(response_lines) - 16} lines collapsed) ...')}")
                    for line in response_lines[-8:]:
                        print(f"  {_render_markdown(line)}")
                    print()
                    print(f"  {dim(f'Ctrl+O to expand ({len(response_lines)} lines) · any key to continue')}")

                def _show_expanded():
                    print(f"  {agent_label} › ")
                    for line in response_lines:
                        print(f"  {_render_markdown(line)}")
                    print()
                    print(f"  {dim(f'Ctrl+O to collapse · any key to continue')}")

                def _count_display_lines(expanded: bool) -> int:
                    if expanded:
                        return len(response_lines) + 3  # agent label + lines + blank + hint
                    else:
                        return 8 + 1 + 8 + 3  # first8 + collapsed + last8 + agent+blank+hint

                _show_collapsed()

                try:
                    import tty
                    import termios
                    fd = sys.stdin.fileno()
                    old_settings = termios.tcgetattr(fd)
                    try:
                        while True:
                            tty.setraw(fd)
                            ch = sys.stdin.read(1)
                            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

                            if ord(ch) == 15:  # Ctrl+O — toggle
                                # Clear current display
                                clear_count = _count_display_lines(_is_expanded)
                                for _ in range(clear_count):
                                    sys.stdout.write(f"\033[A\033[2K")
                                sys.stdout.flush()

                                _is_expanded = not _is_expanded
                                if _is_expanded:
                                    _show_expanded()
                                else:
                                    _show_collapsed()
                            else:
                                # Any other key — continue
                                break
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except (ImportError, OSError, ValueError):
                    pass
                print()

            # Show elapsed time
            elapsed = _time.monotonic() - _response_start
            print(f"  {dim(f'✻ Response took {_format_elapsed(elapsed)}')}")
            print()

            # Agentic loop: detect commands → run → feed output back → agent continues
            if full_response:
                commands = _extract_commands("".join(full_response))
                if commands:
                    try:
                        exec_results = _offer_run_commands(commands, state.get("repo_path", cwd), agent_name=current_agent)
                    except (EOFError, KeyboardInterrupt):
                        print()
                        exec_results = []
                    except Exception as e:
                        print(red(f"\n  Command execution error: {e}"))
                        exec_results = []

                    # Feed execution results back to the agent automatically
                    if exec_results:
                        feedback_parts = []
                        for er in exec_results:
                            output_preview = er["output"][:2000] if er["output"] else "(no output)"
                            feedback_parts.append(
                                f"Command: {er['command']}\nOutput:\n{output_preview}"
                            )
                        feedback = (
                            "I ran the following commands. Here are the results. "
                            "Please analyze the output and suggest next steps if needed.\n\n"
                            + "\n\n---\n\n".join(feedback_parts)
                        )

                        print(dim("  Feeding results back to agent..."))
                        print()

                        # Send follow-up to agent with results
                        followup_messages = [
                            {"role": "system", "content": system_context},
                            {"role": "user", "content": feedback},
                        ]

                        agent_label = bold(magenta(current_agent))
                        sys.stdout.write(f"  {agent_label} › ")
                        sys.stdout.flush()

                        for piece_type, piece_content in _stream_chat(
                            url, current_agent, followup_messages,
                            state.get("session_id"),
                            cwd=state.get("repo_path"),
                        ):
                            if piece_type == "text":
                                sys.stdout.write(_render_markdown(piece_content))
                                sys.stdout.flush()
                            elif piece_type == "reasoning":
                                sys.stdout.write(f"\n    {dim(piece_content.strip())}")
                                sys.stdout.flush()
                            elif piece_type == "session_id":
                                state["session_id"] = piece_content
                            elif piece_type == "error":
                                print(red(f"\n  Error: {piece_content}"))

                        print()
                        print()

        except KeyboardInterrupt:
            print()
            print()
            print(dim("  Chat ended. (Ctrl+C)"))
            print()
            break

        except EOFError:
            print()
            print(dim("  Chat ended."))
            print()
            break