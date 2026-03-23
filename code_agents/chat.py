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
        "Jenkins Deploy — Deployment Jobs",
        [
            "Trigger deployment jobs with build numbers",
            "Monitor deployment progress",
            "Fetch deployment logs",
            "Report deployment outcomes",
        ],
        [
            "Deploy build #42 to staging",
            "What's the status of the last deployment?",
            "Show deployment logs for the latest deploy",
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


def _visible_len(text: str) -> int:
    """Return the visible length of a string, ignoring ANSI escape codes."""
    return len(_ANSI_STRIP_RE.sub("", text))


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


def _offer_run_commands(commands: list[str], cwd: str) -> list[dict[str, str]]:
    """
    Offer to run detected shell commands. Returns list of executed results:
    [{"command": "...", "output": "..."}]

    Results can be fed back to the agent for continued reasoning.
    """
    results: list[dict[str, str]] = []

    if not commands:
        return results

    import shutil
    term_width = shutil.get_terminal_size((80, 24)).columns
    box_width = min(term_width - 4, 100)
    inner = box_width - 2

    print(red(f"  ┌{'─' * box_width}┐"))
    title = f" {bold(cyan('Commands detected:'))}"
    print(red(f"  │") + title + " " * max(0, inner - len("Commands detected:") - 1) + red("│"))
    print(red(f"  ├{'─' * box_width}┤"))
    for i, cmd in enumerate(commands, 1):
        display = cmd if len(cmd) <= (inner - 6) else cmd[:inner - 9] + "..."
        line = f" {bold(str(i) + '.')} {cyan(display)}"
        visible_len = len(f" {i}. {display}")
        pad = max(0, inner - visible_len)
        print(red(f"  │") + line + " " * pad + red("│"))
    print(red(f"  └{'─' * box_width}┘"))
    print()

    for i, cmd in enumerate(commands, 1):
        display = cmd if len(cmd) <= 60 else cmd[:57] + "..."
        try:
            answer = input(
                f"  Run [{bold(str(i))}] {display}? [y/N/all/skip]: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return results

        if answer == "skip":
            print(dim("  Skipped remaining commands."))
            return results
        elif answer == "all":
            for remaining_cmd in commands[i - 1:]:
                resolved = _resolve_placeholders(remaining_cmd)
                if resolved:
                    output = _run_single_command(resolved, cwd)
                    results.append({"command": resolved, "output": output})
            return results
        elif answer in ("y", "yes"):
            resolved = _resolve_placeholders(cmd)
            if resolved:
                output = _run_single_command(resolved, cwd)
                results.append({"command": resolved, "output": output})
        else:
            print(dim(f"  Skipped."))

    return results


def _run_single_command(cmd: str, cwd: str) -> str:
    """Run a single shell command, display in red box, and return raw output."""
    import subprocess
    import shutil

    term_width = shutil.get_terminal_size((80, 24)).columns
    box_width = min(term_width - 4, 100)
    inner_width = box_width - 2

    def _box_line(text: str) -> str:
        visible = text[:inner_width]
        pad = max(0, inner_width - len(visible))
        return red(f"  │") + f" {visible}{' ' * pad}" + red("│")

    # Top border + command
    print(red(f"  ┌{'─' * box_width}┐"))
    print(red(f"  │") + f" {bold('$')} {cyan(cmd[:inner_width - 4])}" + " " * max(0, inner_width - len(cmd) - 3) + red("│"))
    print(red(f"  ├{'─' * box_width}┤"))

    raw_output = ""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        raw_output = (result.stdout or "") + (result.stderr or "")
        display_lines = []
        if result.stdout:
            stdout = result.stdout
            try:
                import json as _json
                parsed = _json.loads(stdout)
                stdout = _json.dumps(parsed, indent=2, ensure_ascii=False)
            except (ValueError, TypeError):
                pass
            display_lines.extend(stdout.splitlines())
        if result.stderr:
            display_lines.extend(result.stderr.splitlines())

        if display_lines:
            for line in display_lines[:50]:
                print(_box_line(line))
            if len(display_lines) > 50:
                print(_box_line(f"... ({len(display_lines) - 50} more lines)"))

        if result.returncode != 0:
            status = red(f"  │ ✗ Exit code: {result.returncode}")
            pad = max(0, inner_width - len(f" ✗ Exit code: {result.returncode}"))
            print(status + " " * pad + red("│"))
            raw_output += f"\n[exit code: {result.returncode}]"
        else:
            status_text = " ✓ Done"
            pad = max(0, inner_width - len(status_text))
            print(red("  │") + green(status_text) + " " * pad + red("│"))

    except subprocess.TimeoutExpired:
        print(_box_line(red("Timed out (120s)")))
        raw_output = "[timed out after 120s]"
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
        # Manual run: /run <command>
        if not arg:
            print(yellow("  Usage: /run <shell command>"))
            return None
        _run_single_command(arg, state.get("repo_path", "."))
        return None

    elif command == "/help":
        print()
        print(bold("  Chat Commands:"))
        print(f"    {cyan('/quit'):<16} Exit chat")
        print(f"    {cyan('/agent <name>'):<16} Switch to another agent permanently")
        print(f"    {cyan('/agents'):<16} List all available agents")
        print(f"    {cyan('/run <cmd>'):<16} Run a shell command in the repo directory")
        print(f"    {cyan('/restart'):<16} Restart the server")
        print(f"    {cyan('/rules'):<16} Show active rules for current agent")
        print(f"    {cyan('/session'):<16} Show current session ID")
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
        print(green("  ✓ Session cleared. Next message starts fresh."))

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
    }

    # Tab-completion for slash commands and agent names
    _slash_commands = ["/help", "/quit", "/exit", "/agents", "/agent", "/run", "/restart", "/rules", "/session", "/clear"]
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
    print(dim("  Commands: /help /quit /agents /agent <name> /session /clear"))
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

                    # Build messages with repo context + rules
                    repo = state.get("repo_path", cwd)
                    repo_name = os.path.basename(repo)

                    from .rules_loader import load_rules as _load_rules
                    delegate_rules = _load_rules(delegate_agent, repo)

                    system_context = (
                        f"IMPORTANT: You are working on the project at: {repo}\n"
                        f"Project name: {repo_name}\n"
                        f"This is the user's repository — all your analysis, code reading, "
                        f"file operations, and responses must be about THIS project's files. "
                        f"Do NOT describe the code-agents tool itself.\n"
                        f"When reading files, searching code, or explaining architecture — "
                        f"always operate within {repo}."
                    )
                    if delegate_rules:
                        system_context += f"\n\n--- Rules ---\n{delegate_rules}\n--- End Rules ---"
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
                            sys.stdout.write(piece_content)
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
                            _offer_run_commands(cmds, state.get("repo_path", cwd))

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
                continue

            # Build messages — inject repo context + rules
            repo = state.get("repo_path", cwd)
            repo_name = os.path.basename(repo)
            current_agent = state["agent"]

            # Load rules fresh from disk (auto-refresh on every message)
            from .rules_loader import load_rules as _load_rules
            rules_text = _load_rules(current_agent, repo)

            system_context = (
                f"IMPORTANT: You are working on the project at: {repo}\n"
                f"Project name: {repo_name}\n"
                f"This is the user's repository — all your analysis, code reading, "
                f"file operations, and responses must be about THIS project's files. "
                f"Do NOT describe the code-agents tool itself.\n"
                f"When reading files, searching code, or explaining architecture — "
                f"always operate within {repo}."
            )
            if rules_text:
                system_context += f"\n\n--- Rules ---\n{rules_text}\n--- End Rules ---"
            messages = [
                {"role": "system", "content": system_context},
                {"role": "user", "content": user_input},
            ]

            # Stream response
            current_agent = state["agent"]
            agent_label = bold(magenta(current_agent))
            sys.stdout.write(f"\n  {agent_label} › ")
            sys.stdout.flush()

            got_text = False
            full_response: list[str] = []
            for piece_type, piece_content in _stream_chat(
                url, current_agent, messages, state.get("session_id"),
                cwd=state.get("repo_path"),
            ):
                if piece_type == "text":
                    got_text = True
                    full_response.append(piece_content)
                    sys.stdout.write(piece_content)
                    sys.stdout.flush()

                elif piece_type == "reasoning":
                    # Show tool activity in dimmed style
                    if "Using tool:" in piece_content:
                        sys.stdout.write(f"\n    {dim(piece_content.strip())}")
                    else:
                        sys.stdout.write(f"\n    {dim(piece_content.strip())}")
                    sys.stdout.flush()

                elif piece_type == "session_id":
                    state["session_id"] = piece_content

                elif piece_type == "error":
                    print(red(f"\n  Error: {piece_content}"))

            if got_text:
                print()  # Newline after response
            print()  # Blank line between turns

            # Agentic loop: detect commands → run → feed output back → agent continues
            if full_response:
                commands = _extract_commands("".join(full_response))
                if commands:
                    exec_results = _offer_run_commands(commands, state.get("repo_path", cwd))

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
                                sys.stdout.write(piece_content)
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