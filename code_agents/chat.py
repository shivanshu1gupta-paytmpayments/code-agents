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

# Interactive CLI chat REPL for Code Agents.
#
# Split into modules:
#   chat_ui.py      — colors, spinners, selectors, markdown, welcome boxes
#   chat_commands.py — command extraction, execution, placeholders, trust
#   chat_server.py  — server communication, streaming, health checks
#   chat.py         — this file: REPL loop, slash commands, agent data

import json
import os
import re
import sys
import time as _time_mod
from datetime import datetime
from pathlib import Path
from typing import Optional

# Re-export from split modules so existing imports (tests, etc.) still work
from .chat_ui import (  # noqa: F401
    bold, green, yellow, red, cyan, dim, magenta,
    _rl_bold, _rl_green, _USE_COLOR,
    _visible_len, _render_markdown, _spinner,
    _ask_yes_no, _tab_selector,
    _print_welcome as _print_welcome_raw,
)
from .chat_commands import (  # noqa: F401
    _extract_commands, _resolve_placeholders,
    _offer_run_commands, _run_single_command,
    _save_command_to_rules, _is_command_trusted,
)
from .chat_server import (  # noqa: F401
    _server_url, _check_server, _check_workspace_trust,
    _get_agents, _stream_chat,
)

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
    "jenkins-cicd": "Build and deploy via Jenkins — end-to-end CI/CD",
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
    "jenkins-cicd": (
        "Jenkins CI/CD — Build & Deploy",
        [
            "Build a service (trigger, poll, extract version)",
            "Deploy using the build version — all in one session",
            "List jobs, fetch parameters, monitor progress",
            "Full build → deploy → verify recommendation",
        ],
        [
            "Build and deploy pg-acquiring-biz to dev",
            "Build release branch with java 21",
            "Deploy version 1.2.3 to dev-stable",
            "What's the status of the last build?",
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


# Helpers moved to: chat_ui.py, chat_commands.py, chat_server.py
# Re-exported at top of this file for backward compatibility.


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


# _print_welcome, _server_url, _check_server, _check_workspace_trust,
# _get_agents, _stream_chat, _extract_commands, _resolve_placeholders,
# _offer_run_commands, _run_single_command — all moved to split modules.
# Re-exported at top of this file.
# (575 lines of duplicate code removed — now in chat_ui.py, chat_commands.py, chat_server.py)


def _print_welcome(agent_name: str) -> None:
    """Print welcome for an agent using AGENT_WELCOME dict."""
    _print_welcome_raw(agent_name, AGENT_WELCOME)


# ---------------------------------------------------------------------------
# Completer, slash commands, and REPL loop
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