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


def _stream_chat(url: str, agent: str, messages: list[dict], session_id: Optional[str] = None):
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
# Slash command handlers
# ---------------------------------------------------------------------------


def _handle_command(cmd: str, state: dict, url: str) -> Optional[str]:
    """
    Handle a slash command. Returns None to continue, or "quit" to exit.
    Modifies state dict in-place.
    """
    parts = cmd.strip().split(None, 1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command in ("/quit", "/exit", "/q"):
        return "quit"

    elif command == "/help":
        print()
        print(bold("  Chat Commands:"))
        print(f"    {cyan('/quit'):<16} Exit chat")
        print(f"    {cyan('/agent <name>'):<16} Switch to another agent")
        print(f"    {cyan('/agents'):<16} List all available agents")
        print(f"    {cyan('/session'):<16} Show current session ID")
        print(f"    {cyan('/clear'):<16} Clear session (fresh start, same agent)")
        print(f"    {cyan('/help'):<16} Show this help")
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
        print(f"    Role: {dim(role)}")
        print(f"    Session: {dim('new')}")
        print()

    elif command == "/session":
        sid = state.get("session_id")
        if sid:
            print(f"  Session: {cyan(sid)}")
        else:
            print(dim("  No active session (will be created on first message)"))

    elif command == "/clear":
        state["session_id"] = None
        print(green("  ✓ Session cleared. Next message starts fresh."))

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

    # Load .env
    cwd = os.getcwd()
    env_file = os.path.join(cwd, ".env")
    if os.path.exists(env_file):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=True)
        except ImportError:
            pass
    os.environ.setdefault("TARGET_REPO_PATH", cwd)

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

    # State
    state = {
        "agent": agent_name,
        "session_id": None,
    }

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
    print(f"  Repo:    {cyan(cwd)}")
    print(f"  Server:  {dim(url)}")
    print()
    print(dim("  Commands: /help /quit /agents /agent <name> /session /clear"))
    print()

    # REPL
    while True:
        try:
            # Read input (supports multi-line with \ continuation)
            lines = []
            prompt_str = f"  {bold(green('you'))} › "
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
                result = _handle_command(user_input, state, url)
                if result == "quit":
                    print()
                    print(dim("  Chat ended."))
                    print()
                    break
                continue

            # Build messages
            messages = [{"role": "user", "content": user_input}]

            # Stream response
            current_agent = state["agent"]
            agent_label = bold(magenta(current_agent))
            sys.stdout.write(f"\n  {agent_label} › ")
            sys.stdout.flush()

            got_text = False
            for piece_type, piece_content in _stream_chat(
                url, current_agent, messages, state.get("session_id")
            ):
                if piece_type == "text":
                    got_text = True
                    sys.stdout.write(piece_content)
                    sys.stdout.flush()

                elif piece_type == "reasoning":
                    # Show tool activity in dimmed style
                    # Extract tool name if present
                    if "Using tool:" in piece_content:
                        # Format: > **Using tool: read_file**
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