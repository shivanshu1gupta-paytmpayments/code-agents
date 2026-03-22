"""
Code Agents CLI — unified entry point for all commands.

Usage:
    code-agents <command> [options]

Run 'code-agents help' for full command list.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_code_agents_home() -> Path:
    """Find where code-agents is installed."""
    return Path(__file__).resolve().parent.parent


def _user_cwd() -> str:
    """Get the user's REAL working directory.

    When run via the wrapper script (~/.local/bin/code-agents),
    the wrapper does 'cd ~/.code-agents' before invoking poetry,
    so os.getcwd() returns ~/.code-agents — not the user's repo.

    The wrapper sets CODE_AGENTS_USER_CWD to the original directory.
    """
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def _load_env():
    """Load env from global config + per-repo overrides."""
    from .env_loader import load_all_env
    load_all_env(_user_cwd())


def _colors():
    """Import color helpers lazily."""
    from .setup import bold, green, yellow, red, cyan, dim
    return bold, green, yellow, red, cyan, dim


def _server_url() -> str:
    host = os.getenv("HOST", "127.0.0.1")
    port = os.getenv("PORT", "8000")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def _api_get(path: str) -> dict | list | None:
    """Make a GET request to the running server. Returns None on failure."""
    import httpx
    try:
        r = httpx.get(f"{_server_url()}{path}", timeout=5.0)
        return r.json()
    except Exception:
        return None


def _api_post(path: str, body: dict | None = None) -> dict | list | None:
    """Make a POST request to the running server."""
    import httpx
    try:
        r = httpx.post(f"{_server_url()}{path}", json=body or {}, timeout=30.0)
        return r.json()
    except Exception as e:
        bold, _, _, red, _, _ = _colors()
        print(red(f"  Error: {e}"))
        return None


# ============================================================================
# COMMANDS
# ============================================================================


def cmd_init():
    """Initialize code-agents in the current repository."""
    from .setup import (
        prompt, prompt_yes_no, prompt_choice, prompt_cicd_pipeline,
        prompt_integrations, write_env_file, validate_url,
    )
    bold, green, yellow, red, cyan, dim = _colors()

    cwd = _user_cwd()
    code_agents_home = _find_code_agents_home()

    print()
    print(bold(cyan("  ╔══════════════════════════════════════════════╗")))
    print(bold(cyan("  ║       Code Agents — Init Repository          ║")))
    print(bold(cyan("  ╚══════════════════════════════════════════════╝")))
    print()

    if os.path.isdir(os.path.join(cwd, ".git")):
        print(green(f"  ✓ Git repo detected: {cwd}"))
    else:
        print(yellow(f"  ! No .git found in: {cwd}"))
        if not prompt_yes_no("Continue anyway?", default=False):
            print(yellow("  Cancelled."))
            return

    print(f"  Code Agents installed at: {dim(str(code_agents_home))}")
    print()

    env_vars: dict[str, str] = {"TARGET_REPO_PATH": cwd}

    # Backend
    print(bold("  Backend Configuration"))
    choice = prompt_choice("Which backend?", ["Cursor (default)", "Claude", "Both"], default=1)
    if choice in (1, 3):
        env_vars["CURSOR_API_KEY"] = prompt("CURSOR_API_KEY", secret=True, required=True)
        url = prompt("Cursor API URL (blank for CLI mode)", validator=validate_url, error_msg="Must be a valid URL")
        if url:
            env_vars["CURSOR_API_URL"] = url
    if choice in (2, 3):
        env_vars["ANTHROPIC_API_KEY"] = prompt("ANTHROPIC_API_KEY", secret=True, required=True)
    print()

    # Server
    print(bold("  Server Configuration"))
    env_vars["HOST"] = prompt("HOST", default="0.0.0.0")
    env_vars["PORT"] = prompt("PORT", default="8000")
    print()

    # CI/CD & integrations
    env_vars.update(prompt_cicd_pipeline())
    env_vars.update(prompt_integrations())

    env_vars = {k: v for k, v in env_vars.items() if v}

    print(bold("━" * 44))
    original_dir = _user_cwd()
    os.chdir(cwd)
    write_env_file(env_vars)
    os.chdir(original_dir)

    print()
    from .env_loader import GLOBAL_ENV_PATH, PER_REPO_FILENAME
    print(green(f"  ✓ Initialized in: {cwd}"))
    print(f"  Global config: {cyan(str(GLOBAL_ENV_PATH))}")
    print(f"  Repo config:   {cyan(os.path.join(cwd, PER_REPO_FILENAME))}")
    print()

    if prompt_yes_no("Start the server now?", default=True):
        _start_background(cwd)
    else:
        print()
        print(bold("  Next steps:"))
        print(f"    code-agents start       {dim('# start the server')}")
        print(f"    code-agents status      {dim('# check server health')}")
        print(f"    code-agents agents      {dim('# list available agents')}")
        print()


def cmd_rules(rest: list[str] | None = None):
    """Manage rules files (list, create, edit, delete)."""
    import subprocess as _sp
    rest = rest or []
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()

    subcmd = rest[0] if rest else "list"

    if subcmd == "list":
        agent_name = None
        for i, arg in enumerate(rest):
            if arg == "--agent" and i + 1 < len(rest):
                agent_name = rest[i + 1]

        from .rules_loader import list_rules
        rules = list_rules(agent_name=agent_name, repo_path=cwd)
        print()
        if not rules:
            print(dim("  No rules found."))
            print()
            print(f"  Create one:")
            print(f"    code-agents rules create                  {dim('# project rule, all agents')}")
            print(f"    code-agents rules create --agent code-writer  {dim('# project rule, specific agent')}")
            print(f"    code-agents rules create --global         {dim('# global rule, all agents')}")
        else:
            print(bold("  Active Rules:"))
            print()
            for r in rules:
                scope_label = green("global") if r["scope"] == "global" else cyan("project")
                target_label = "all agents" if r["target"] == "_global" else r["target"]
                print(f"    [{scope_label}] {bold(target_label)}")
                print(f"      {dim(r['preview'])}")
                print(f"      {dim(r['path'])}")
                print()
        print()

    elif subcmd == "create":
        is_global = "--global" in rest
        agent_name = None
        for i, arg in enumerate(rest):
            if arg == "--agent" and i + 1 < len(rest):
                agent_name = rest[i + 1]

        if is_global:
            from .rules_loader import GLOBAL_RULES_DIR
            rules_dir = GLOBAL_RULES_DIR
        else:
            rules_dir = Path(cwd) / ".code-agents" / "rules"

        filename = f"{agent_name}.md" if agent_name else "_global.md"
        filepath = rules_dir / filename

        rules_dir.mkdir(parents=True, exist_ok=True)
        if not filepath.exists():
            target_desc = agent_name or "all agents"
            scope_desc = "global" if is_global else "project"
            filepath.write_text(
                f"# Rules for {target_desc} ({scope_desc})\n\n"
                f"<!-- Write your rules below. These will be injected into the agent's system prompt. -->\n\n"
            )
            print(green(f"  ✓ Created: {filepath}"))
        else:
            print(dim(f"  File exists: {filepath}"))

        editor = os.environ.get("EDITOR", "vi")
        print(dim(f"  Opening in {editor}..."))
        _sp.run([editor, str(filepath)])

    elif subcmd == "edit":
        if len(rest) < 2:
            print(yellow("  Usage: code-agents rules edit <path>"))
            return
        filepath = rest[1]
        if not os.path.isfile(filepath):
            print(red(f"  File not found: {filepath}"))
            return
        editor = os.environ.get("EDITOR", "vi")
        _sp.run([editor, filepath])

    elif subcmd == "delete":
        if len(rest) < 2:
            print(yellow("  Usage: code-agents rules delete <path>"))
            return
        filepath = rest[1]
        if not os.path.isfile(filepath):
            print(red(f"  File not found: {filepath}"))
            return
        try:
            answer = input(f"  Delete {filepath}? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer in ("y", "yes"):
            os.remove(filepath)
            print(green(f"  ✓ Deleted: {filepath}"))
        else:
            print(dim("  Cancelled."))

    else:
        print(yellow(f"  Unknown subcommand: {subcmd}"))
        print(f"  Usage: code-agents rules [list|create|edit|delete]")


def cmd_migrate():
    """Migrate legacy .env to centralized config."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()

    legacy = os.path.join(cwd, ".env")
    if not os.path.isfile(legacy):
        print()
        print(dim("  No legacy .env file found — nothing to migrate."))
        print()
        return

    from .setup import parse_env_file
    from .env_loader import GLOBAL_ENV_PATH, PER_REPO_FILENAME, split_vars

    env_vars = parse_env_file(Path(legacy))
    if not env_vars:
        print()
        print(dim("  Legacy .env is empty — nothing to migrate."))
        print()
        return

    global_vars, repo_vars = split_vars(env_vars)

    print()
    print(bold("  Migrating .env to centralized config"))
    print()
    print(f"    Source:        {legacy} ({len(env_vars)} variables)")
    print(f"    Global config: {GLOBAL_ENV_PATH} ({len(global_vars)} variables)")
    print(f"    Repo config:   {os.path.join(cwd, PER_REPO_FILENAME)} ({len(repo_vars)} variables)")
    print()

    if global_vars:
        print(f"  {bold('Global')} (API keys, server, integrations):")
        for k in sorted(global_vars):
            print(f"    {dim(k)}")
        print()
    if repo_vars:
        print(f"  {bold('Per-repo')} (Jenkins, ArgoCD, testing):")
        for k in sorted(repo_vars):
            print(f"    {dim(k)}")
        print()

    try:
        answer = input(f"  Proceed with migration? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if answer not in ("", "y", "yes"):
        print(dim("  Cancelled."))
        return

    from .setup import _write_env_to_path

    if global_vars:
        # Merge with existing global config
        existing_global = parse_env_file(GLOBAL_ENV_PATH) if GLOBAL_ENV_PATH.is_file() else {}
        merged_global = dict(existing_global)
        for k, v in global_vars.items():
            merged_global[k] = v
        GLOBAL_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        _write_env_to_path(GLOBAL_ENV_PATH, merged_global, "global config")

    if repo_vars:
        repo_path = Path(os.path.join(cwd, PER_REPO_FILENAME))
        existing_repo = parse_env_file(repo_path) if repo_path.is_file() else {}
        merged_repo = dict(existing_repo)
        for k, v in repo_vars.items():
            merged_repo[k] = v
        _write_env_to_path(repo_path, merged_repo, "repo config")

    # Backup legacy .env
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{legacy}.backup.{ts}"
    import shutil
    shutil.move(legacy, backup)
    print(green(f"  ✓ Legacy .env moved to: {backup}"))
    print()
    print(green(bold("  Migration complete!")))
    print()


def _start_background(repo_path: str):
    """Start the server in background and show a clean summary."""
    bold, green, yellow, red, cyan, dim = _colors()

    from .env_loader import load_all_env
    load_all_env(repo_path)

    os.environ["TARGET_REPO_PATH"] = repo_path
    host = os.getenv("HOST", "0.0.0.0")
    port = os.getenv("PORT", "8000")
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    base_url = f"http://{display_host}:{port}"
    log_file = _find_code_agents_home() / "logs" / "code-agents.log"

    # Start server as a background subprocess
    code_agents_home = str(_find_code_agents_home())
    server_cmd = [
        sys.executable, "-m", "code_agents.main",
    ]
    env = os.environ.copy()
    env["TARGET_REPO_PATH"] = repo_path

    import subprocess
    proc = subprocess.Popen(
        server_cmd,
        cwd=code_agents_home,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=open(str(log_file), "a") if log_file.parent.exists() else subprocess.DEVNULL,
    )

    # Wait briefly and check it started
    import time
    time.sleep(2)
    if proc.poll() is not None:
        print(red("  ✗ Server failed to start. Check logs:"))
        print(f"    {dim(str(log_file))}")
        print()
        return

    # Verify health
    healthy = False
    try:
        import httpx
        r = httpx.get(f"{base_url}/health", timeout=5.0)
        healthy = r.status_code == 200
    except Exception:
        pass

    print()
    if healthy:
        print(green(bold("  ✓ Code Agents is running!")))
    else:
        print(yellow("  ⏳ Server is starting up (may take a few seconds)..."))

    print()
    print(f"  {bold('Target repo:')}  {repo_path}")
    print(f"  {bold('Logs:')}         {log_file}")
    print(f"  {bold('PID:')}          {proc.pid}")
    print()
    print(f"  {bold('Verify (copy & paste in another terminal):')}")
    print()
    print(f"    {dim('# Health check')}")
    print(f"    curl -s {base_url}/health | python3 -m json.tool")
    print()
    print(f"    {dim('# List all agents')}")
    print(f"    curl -s {base_url}/v1/agents | python3 -m json.tool")
    print()
    print(f"    {dim('# Full diagnostics')}")
    print(f"    curl -s {base_url}/diagnostics | python3 -m json.tool")
    print()
    print(f"    {dim('# Send a prompt to an agent')}")
    print(f"    curl -s -X POST {base_url}/v1/agents/code-reasoning/chat/completions \\")
    print(f"      -H 'Content-Type: application/json' \\")
    print(f"      -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"What files are in this project?\"}}]}}' \\")
    print(f"      | python3 -m json.tool")
    print()
    print(f"  {bold('CLI commands:')}")
    print(f"    code-agents status                  {dim('# check server health')}")
    print(f"    code-agents agents                  {dim('# list agents')}")
    print(f"    code-agents logs                    {dim('# tail logs')}")
    print(f"    code-agents test                    {dim('# run tests')}")
    print(f"    code-agents diff main HEAD          {dim('# see changes')}")
    print(f"    code-agents pipeline start           {dim('# start CI/CD')}")
    print(f"    code-agents shutdown                 {dim('# stop the server')}")
    print()


def _check_workspace_trust(repo_path: str) -> bool:
    """
    Check and auto-trust cursor-agent workspace for the target repo.

    If the workspace is not trusted, automatically trusts it using
    cursor-agent --trust --print. Returns True if trust is OK.
    """
    import shutil
    import subprocess

    bold, green, yellow, red, cyan, dim = _colors()

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


def cmd_start():
    """Start the server in background pointing at the current directory."""
    _load_env()
    cwd = _user_cwd()

    # Pre-flight: check workspace trust before starting server
    if not _check_workspace_trust(cwd):
        return

    # Foreground mode only if explicitly requested (for debugging)
    if "--fg" in sys.argv or "--foreground" in sys.argv:
        bold, green, _, _, cyan, dim = _colors()
        host = os.getenv("HOST", "0.0.0.0")
        port = os.getenv("PORT", "8000")
        print()
        print(bold(cyan("  Starting Code Agents (foreground)...")))
        print(dim(f"  Target repo: {cwd}"))
        print(dim(f"  Server:      http://{host}:{port}"))
        print(dim(f"  Logs:        {_find_code_agents_home()}/logs/code-agents.log"))
        print(dim("  Press Ctrl+C to stop"))
        print()
        from .main import main as run_server
        run_server()
        return

    _start_background(cwd)


def cmd_shutdown():
    """Shutdown the running code-agents server by killing the process on its port."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    port = os.getenv("PORT", "8000")

    print()
    print(bold(f"  Shutting down Code Agents on port {port}..."))

    # Find process on the port
    try:
        result = subprocess.run(
            ["lsof", f"-ti:{port}"],
            capture_output=True, text=True,
        )
        pids = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
        if pids:
            for pid in pids:
                os.kill(int(pid), 15)  # SIGTERM
            import time
            time.sleep(1)
            # Verify killed
            check = subprocess.run(["lsof", f"-ti:{port}"], capture_output=True, text=True)
            remaining = [p.strip() for p in check.stdout.strip().splitlines() if p.strip()]
            if remaining:
                # Force kill
                for pid in remaining:
                    os.kill(int(pid), 9)  # SIGKILL
                print(green(f"  ✓ Server force-stopped (PID: {', '.join(pids)})"))
            else:
                print(green(f"  ✓ Server stopped (PID: {', '.join(pids)})"))
        else:
            print(green(f"  ✓ No server running on port {port}"))
    except Exception as e:
        print(yellow(f"  Could not find server process on port {port}: {e}"))
        print(f"  Try manually: {bold(f'kill $(lsof -ti:{port})')}")
    print()


def cmd_restart():
    """Restart the code-agents server (shutdown + start)."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    port = os.getenv("PORT", "8000")

    print()
    print(bold(cyan("  Restarting Code Agents...")))
    print()

    # Shutdown
    try:
        result = subprocess.run(
            ["lsof", f"-ti:{port}"],
            capture_output=True, text=True,
        )
        pids = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
        if pids:
            for pid in pids:
                os.kill(int(pid), 15)  # SIGTERM
            import time
            time.sleep(1)
            # Force kill stragglers
            check = subprocess.run(["lsof", f"-ti:{port}"], capture_output=True, text=True)
            remaining = [p.strip() for p in check.stdout.strip().splitlines() if p.strip()]
            for pid in remaining:
                os.kill(int(pid), 9)  # SIGKILL
            print(green(f"  ✓ Server stopped (PID: {', '.join(pids)})"))
        else:
            print(dim(f"  No server was running on port {port}"))
    except Exception as e:
        print(yellow(f"  Could not stop server: {e}"))

    # Start
    print()
    _start_background(cwd)


def cmd_status():
    """Check server health and show configuration."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    print()
    print(bold("  Code Agents Status"))
    print(bold("  " + "─" * 40))

    # Check if server is running
    data = _api_get("/health")
    if data and data.get("status") == "ok":
        print(green("  ✓ Server is running"))
    else:
        print(red("  ✗ Server is not running"))
        print(dim(f"    Start with: code-agents start"))
        print()
        # Still show local config
        cwd = _user_cwd()
        env_file = os.path.join(cwd, ".env")
        print(f"  Repo:     {cyan(cwd)}")
        print(f"  .env:     {'exists' if os.path.exists(env_file) else red('not found — run: code-agents init')}")
        print()
        return

    # Get diagnostics
    url = _server_url()
    diag = _api_get("/diagnostics")
    if diag:
        print(f"  URL:      {cyan(url)}")
        print(f"  Version:  {diag.get('package_version', '?')}")
        print(f"  Agents:   {len(diag.get('agents', []))}")
        print(f"  Repo:     {cyan(os.getenv('TARGET_REPO_PATH', _user_cwd()))}")
        print()
        print(bold("  Integrations:"))
        print(f"    Jenkins:       {'✓ configured' if diag.get('jenkins_configured') else '✗ not configured'}")
        print(f"    ArgoCD:        {'✓ configured' if diag.get('argocd_configured') else '✗ not configured'}")
        print(f"    Elasticsearch: {'✓ configured' if diag.get('elasticsearch_configured') else '✗ not configured'}")
        print(f"    Pipeline:      {'✓ enabled' if diag.get('pipeline_enabled') else '✗ not enabled'}")
        print()
        print(bold("  Quick curl commands:"))
        print(f"    curl -s {url}/health | python3 -m json.tool")
        print(f"    curl -s {url}/v1/agents | python3 -m json.tool")
        print(f"    curl -s {url}/diagnostics | python3 -m json.tool")
    print()


def cmd_agents():
    """List all available agents."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    data = _api_get("/v1/agents")
    if not data:
        # Server not running — load agents from YAML directly
        print(bold("  Available Agents (from YAML):"))
        print()
        try:
            from .config import agent_loader
            agent_loader.load()
            agents = agent_loader.list_agents()
            for a in agents:
                print(f"    {cyan(a.name):<28} {dim(a.display_name or '')}")
                print(f"      backend={a.backend}  model={a.model}  permission={a.permission_mode}")
            print(f"\n  Total: {bold(str(len(agents)))} agents")
        except Exception as e:
            print(red(f"  Error loading agents: {e}"))
        print()
        return

    # Server may return {"data": [...]}, {"agents": [...]}, or a plain list
    if isinstance(data, dict):
        agents = data.get("data") or data.get("agents") or []
    elif isinstance(data, list):
        agents = data
    else:
        agents = []
    print()
    print(bold("  Available Agents:"))
    print()
    for a in agents:
        name = a.get("name", "?")
        display = a.get("display_name", "")
        endpoint = a.get("endpoint", f"/v1/agents/{name}/chat/completions")
        print(f"    {cyan(name):<28} {dim(display)}")
        print(f"      {dim(endpoint)}")
    print(f"\n  Total: {bold(str(len(agents)))} agents")
    print()


def cmd_logs(args: list[str]):
    """Tail the log file."""
    bold, green, yellow, red, cyan, dim = _colors()
    log_file = _find_code_agents_home() / "logs" / "code-agents.log"

    if not log_file.exists():
        print(yellow(f"  No log file yet: {log_file}"))
        print(dim("  Start the server first: code-agents start"))
        return

    lines = args[0] if args else "50"
    print(dim(f"  Tailing {log_file} (last {lines} lines, Ctrl+C to stop)"))
    print()
    os.execvp("tail", ["tail", "-f", "-n", lines, str(log_file)])


def cmd_config():
    """Show current configuration (from .env in current directory)."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    cwd = _user_cwd()
    env_file = os.path.join(cwd, ".env")

    print()
    print(bold("  Code Agents Configuration"))
    print(bold("  " + "─" * 40))
    print(f"  Directory:  {cyan(cwd)}")
    print(f"  .env file:  {green('found') if os.path.exists(env_file) else red('not found')}")
    print()

    if not os.path.exists(env_file):
        print(yellow("  Run 'code-agents init' to create .env"))
        print()
        return

    from .setup import parse_env_file
    env = parse_env_file(Path(env_file))

    # Show config grouped, mask secrets
    secret_keys = {"CURSOR_API_KEY", "ANTHROPIC_API_KEY", "JENKINS_API_TOKEN", "ARGOCD_AUTH_TOKEN",
                   "ATLASSIAN_OAUTH_CLIENT_SECRET", "REDASH_PASSWORD", "REDASH_API_KEY",
                   "ELASTICSEARCH_API_KEY", "ELASTICSEARCH_PASSWORD"}

    groups = [
        ("Core", ["CURSOR_API_KEY", "CURSOR_API_URL", "ANTHROPIC_API_KEY"]),
        ("Server", ["HOST", "PORT", "LOG_LEVEL"]),
        ("Repository", ["TARGET_REPO_PATH", "TARGET_REPO_REMOTE"]),
        ("Testing", ["TARGET_TEST_COMMAND", "TARGET_COVERAGE_THRESHOLD"]),
        ("Jenkins", ["JENKINS_URL", "JENKINS_USERNAME", "JENKINS_API_TOKEN", "JENKINS_BUILD_JOB", "JENKINS_DEPLOY_JOB"]),
        ("ArgoCD", ["ARGOCD_URL", "ARGOCD_AUTH_TOKEN", "ARGOCD_APP_NAME"]),
    ]

    for group_name, keys in groups:
        group_vars = {k: env[k] for k in keys if k in env}
        if group_vars:
            print(f"  {bold(group_name)}:")
            for k, v in group_vars.items():
                if k in secret_keys and v:
                    display = v[:4] + "•" * 8 + v[-4:] if len(v) > 12 else "••••••"
                else:
                    display = v or dim("(empty)")
                print(f"    {k:<30} {display}")
            print()


def cmd_doctor():
    """Diagnose common issues — comprehensive health check."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()
    issues = 0
    warnings = 0

    print()
    print(bold("  Code Agents Doctor"))
    print(bold("  " + "═" * 50))

    # ── Environment ──
    print()
    print(bold("  Environment"))
    print(bold("  " + "─" * 40))

    # Python
    if sys.version_info >= (3, 10):
        print(green(f"  ✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"))
    else:
        print(red(f"  ✗ Python {sys.version_info.major}.{sys.version_info.minor} — requires 3.10+"))
        issues += 1

    # Poetry
    import shutil
    if shutil.which("poetry"):
        print(green("  ✓ Poetry installed"))
    else:
        print(yellow("  ! Poetry not found in PATH"))
        warnings += 1

    # Git
    if shutil.which("git"):
        print(green("  ✓ Git installed"))
    else:
        print(red("  ✗ Git not found — required for git-ops"))
        issues += 1

    # ── Repository ──
    print()
    print(bold("  Repository"))
    print(bold("  " + "─" * 40))

    # Git repo
    git_root = None
    check = cwd
    while True:
        if os.path.isdir(os.path.join(check, ".git")):
            git_root = check
            break
        parent = os.path.dirname(check)
        if parent == check:
            break
        check = parent

    if git_root:
        repo_name = os.path.basename(git_root)
        print(green(f"  ✓ Git repo: {repo_name} ({git_root})"))
    else:
        print(yellow("  ! No git repo detected — chat/git-ops won't know your project"))
        warnings += 1

    # Config files
    from .env_loader import GLOBAL_ENV_PATH, PER_REPO_FILENAME
    from .setup import parse_env_file

    if GLOBAL_ENV_PATH.is_file():
        g_vars = parse_env_file(GLOBAL_ENV_PATH)
        print(green(f"  ✓ Global config: {GLOBAL_ENV_PATH} ({len(g_vars)} variables)"))
    else:
        print(red(f"  ✗ No global config — run: code-agents init"))
        issues += 1

    repo_env = os.path.join(cwd, PER_REPO_FILENAME)
    if os.path.isfile(repo_env):
        r_vars = parse_env_file(Path(repo_env))
        print(green(f"  ✓ Repo config: {repo_env} ({len(r_vars)} variables)"))
    else:
        print(dim(f"  · No repo config ({PER_REPO_FILENAME}) — optional"))

    # Legacy .env fallback
    legacy_env = os.path.join(cwd, ".env")
    if os.path.isfile(legacy_env):
        print(yellow(f"  ! Legacy .env found — consider running: code-agents migrate"))
        warnings += 1
    elif os.path.isdir(legacy_env):
        print(dim(f"  · .env is a directory (ignored)"))

    # ── Backend ──
    print()
    print(bold("  Backend"))
    print(bold("  " + "─" * 40))

    # API keys
    cursor_key = os.getenv("CURSOR_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if cursor_key:
        print(green(f"  ✓ CURSOR_API_KEY set ({cursor_key[:8]}...)"))
    else:
        print(yellow("  ! CURSOR_API_KEY not set"))

    if anthropic_key:
        print(green(f"  ✓ ANTHROPIC_API_KEY set ({anthropic_key[:8]}...)"))
    else:
        print(dim("  · ANTHROPIC_API_KEY not set (optional)"))

    if not cursor_key and not anthropic_key:
        print(red("  ✗ No backend key configured — run: code-agents init"))
        issues += 1

    # Cursor API URL
    cursor_url = os.getenv("CURSOR_API_URL", "")
    if cursor_url:
        print(green(f"  ✓ CURSOR_API_URL set (HTTP mode)"))
    else:
        print(dim("  · CURSOR_API_URL not set (using CLI mode — needs Cursor desktop)"))

    # Workspace trust (only for CLI mode with cursor backend)
    if cursor_key and not cursor_url:
        import shutil as _shutil
        import subprocess as _sp
        cli_path = _shutil.which("cursor-agent")
        if cli_path:
            try:
                _trust_result = _sp.run(
                    [cli_path, "--print", "--output-format", "stream-json", "agent", "-"],
                    cwd=cwd, input="hi", capture_output=True, text=True, timeout=10,
                )
                if "Workspace Trust Required" in (_trust_result.stderr or ""):
                    # Auto-trust with --trust flag
                    print(dim("  · Trusting workspace..."))
                    _fix = _sp.run(
                        [cli_path, "--trust", "--print", "--output-format", "stream-json", "agent", "-"],
                        cwd=cwd, input="hi", capture_output=True, text=True, timeout=15,
                    )
                    if "Workspace Trust Required" not in (_fix.stderr or ""):
                        print(green("  ✓ Workspace auto-trusted by cursor-agent"))
                    else:
                        print(red(f"  ✗ Workspace not trusted — auto-trust failed"))
                        print(dim(f"    Run: cd {cwd} && cursor-agent agent"))
                        issues += 1
                else:
                    print(green("  ✓ Workspace trusted by cursor-agent"))
            except (Exception,):
                print(dim("  · Could not check workspace trust"))

    # cursor-agent-sdk
    try:
        import cursor_agent_sdk
        print(green("  ✓ cursor-agent-sdk installed"))
    except ImportError:
        if cursor_key:
            print(yellow("  ! cursor-agent-sdk not installed (needed for Cursor backend)"))
            warnings += 1
        else:
            print(dim("  · cursor-agent-sdk not installed"))

    # claude-agent-sdk (core dependency)
    try:
        import claude_agent_sdk
        print(green("  ✓ claude-agent-sdk installed"))
    except ImportError:
        print(red("  ✗ claude-agent-sdk not installed — run: poetry install"))
        issues += 1

    # ── Server ──
    print()
    print(bold("  Server"))
    print(bold("  " + "─" * 40))

    url = _server_url()
    data = _api_get("/health")
    if data and data.get("status") == "ok":
        print(green(f"  ✓ Server running at {url}"))
        # Check agents loaded
        diag = _api_get("/diagnostics")
        if diag:
            agent_count = len(diag.get("agents", []))
            print(green(f"  ✓ {agent_count} agents loaded"))
            print(f"    Version: {diag.get('package_version', '?')}")
    else:
        print(yellow(f"  ! Server not running at {url}"))
        print(dim(f"    Start with: code-agents start"))
        warnings += 1

    # Logs
    log_dir = _find_code_agents_home() / "logs"
    log_file = log_dir / "code-agents.log"
    if log_file.exists():
        size = log_file.stat().st_size
        size_str = f"{size / 1024:.0f}KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f}MB"
        print(green(f"  ✓ Log file: {size_str}"))
    elif log_dir.exists():
        print(dim("  · Log directory exists (no log file yet)"))
    else:
        print(dim("  · No log directory (created on first server start)"))

    # ── Integrations ──
    print()
    print(bold("  Integrations"))
    print(bold("  " + "─" * 40))

    # Jenkins
    jenkins_url = os.getenv("JENKINS_URL", "")
    if jenkins_url:
        jenkins_user = os.getenv("JENKINS_USERNAME", "")
        jenkins_token = os.getenv("JENKINS_API_TOKEN", "")
        jenkins_build = os.getenv("JENKINS_BUILD_JOB", "")
        jenkins_deploy = os.getenv("JENKINS_DEPLOY_JOB", "")
        if jenkins_user and jenkins_token:
            print(green(f"  ✓ Jenkins: {jenkins_url}"))
            if jenkins_build:
                print(f"    Build job: {jenkins_build}")
            else:
                print(yellow("    ! JENKINS_BUILD_JOB not set"))
                warnings += 1
            if jenkins_deploy:
                print(f"    Deploy job: {jenkins_deploy}")
            else:
                print(dim("    · JENKINS_DEPLOY_JOB not set (optional)"))
            # Warn if job looks like a full URL
            for job_var, job_val in [("BUILD", jenkins_build), ("DEPLOY", jenkins_deploy)]:
                if job_val and job_val.startswith("http"):
                    print(red(f"    ✗ JENKINS_{job_var}_JOB looks like a URL — use job path only"))
                    print(dim(f"      e.g. 'pg2/pg2-dev-build-jobs' not '{job_val}'"))
                    issues += 1
        else:
            print(red("  ✗ Jenkins URL set but missing USERNAME or API_TOKEN"))
            issues += 1
    else:
        print(dim("  · Jenkins not configured"))

    # ArgoCD
    argocd_url = os.getenv("ARGOCD_URL", "")
    if argocd_url:
        argocd_token = os.getenv("ARGOCD_AUTH_TOKEN", "")
        argocd_app = os.getenv("ARGOCD_APP_NAME", "")
        if argocd_token:
            print(green(f"  ✓ ArgoCD: {argocd_url}"))
            if argocd_app:
                print(f"    App: {argocd_app}")
            else:
                print(yellow("    ! ARGOCD_APP_NAME not set"))
                warnings += 1
        else:
            print(red("  ✗ ARGOCD_URL set but ARGOCD_AUTH_TOKEN missing"))
            issues += 1
    else:
        print(dim("  · ArgoCD not configured"))

    # Elasticsearch
    es_url = os.getenv("ELASTICSEARCH_URL", "") or os.getenv("ELASTICSEARCH_CLOUD_ID", "")
    if es_url:
        print(green(f"  ✓ Elasticsearch configured"))
    else:
        print(dim("  · Elasticsearch not configured"))

    # Redash
    redash_url = os.getenv("REDASH_BASE_URL", "")
    if redash_url:
        print(green(f"  ✓ Redash: {redash_url}"))
    else:
        print(dim("  · Redash not configured"))

    # ── Summary ──
    print()
    print(bold("  " + "═" * 50))
    if issues == 0 and warnings == 0:
        print(green(bold("  ✓ All checks passed!")))
    elif issues == 0:
        print(yellow(f"  {warnings} warning(s), no critical issues"))
    else:
        print(red(f"  {issues} issue(s), {warnings} warning(s)"))
        print(dim("  Fix issues and run 'code-agents doctor' again"))
    print()


def cmd_diff(args: list[str]):
    """Show git diff between branches."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    base = args[0] if len(args) > 0 else "main"
    head = args[1] if len(args) > 1 else "HEAD"

    cwd = _user_cwd()
    data = _api_get(f"/git/diff?base={base}&head={head}&repo_path={cwd}")
    if not data:
        # Fallback: run git directly
        print(dim(f"  Server not running — using git directly"))
        import asyncio
        from .git_client import GitClient
        client = GitClient(cwd)
        try:
            data = asyncio.run(client.diff(base, head))
        except Exception as e:
            print(red(f"  Error: {e}"))
            return

    print()
    print(bold(f"  Diff: {cyan(base)} → {cyan(head)}"))
    print(f"  Files changed: {data.get('files_changed', 0)}")
    print(f"  Insertions:    {green('+' + str(data.get('insertions', 0)))}")
    print(f"  Deletions:     {red('-' + str(data.get('deletions', 0)))}")
    print()

    for f in data.get("changed_files", []):
        ins = f.get("insertions", 0)
        dels = f.get("deletions", 0)
        print(f"    {green('+' + str(ins)):<8} {red('-' + str(dels)):<8} {f['file']}")
    print()


def cmd_branches():
    """List git branches."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = _user_cwd()

    data = _api_get(f"/git/branches?repo_path={cwd}")
    if not data:
        import asyncio
        from .git_client import GitClient
        client = GitClient(cwd)
        try:
            branches = asyncio.run(client.list_branches())
            data = {"branches": branches}
        except Exception as e:
            print(red(f"  Error: {e}"))
            return

    # Get current branch
    current = None
    cur_data = _api_get(f"/git/current-branch?repo_path={cwd}")
    if cur_data:
        current = cur_data.get("branch")
    else:
        import asyncio
        from .git_client import GitClient
        client = GitClient(cwd)
        try:
            current = asyncio.run(client.current_branch())
        except Exception:
            pass

    print()
    print(bold("  Branches:"))
    for b in data.get("branches", []):
        name = b.get("name", "?")
        marker = f" {green('← current')}" if name == current else ""
        print(f"    {cyan(name)}{marker}")
    print()


def cmd_test(args: list[str]):
    """Run tests on the target repository."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    cwd = _user_cwd()
    branch = args[0] if args else None
    body: dict = {"repo_path": cwd}
    if branch:
        body["branch"] = branch

    print(bold(f"  Running tests in {os.path.basename(cwd)}..."))
    print()

    data = _api_post("/testing/run", body)
    if not data:
        # Fallback: run directly
        import asyncio
        from .testing_client import TestingClient
        client = TestingClient(cwd)
        try:
            data = asyncio.run(client.run_tests(branch=branch))
        except Exception as e:
            print(red(f"  Error: {e}"))
            return

    passed = data.get("passed", False)
    if passed:
        print(green(bold("  ✓ Tests PASSED")))
    else:
        print(red(bold("  ✗ Tests FAILED")))

    print(f"    Total:    {data.get('total', '?')}")
    print(f"    Passed:   {green(str(data.get('passed_count', '?')))}")
    print(f"    Failed:   {red(str(data.get('failed_count', '?')))}")
    print(f"    Errors:   {data.get('error_count', '?')}")
    print(f"    Command:  {dim(data.get('test_command', '?'))}")

    if not passed and data.get("output"):
        print()
        print(bold("  Output (last 30 lines):"))
        lines = data["output"].strip().splitlines()
        for line in lines[-30:]:
            print(f"    {line}")
    print()


def cmd_review(args: list[str]):
    """Review code changes between branches."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    base = args[0] if len(args) > 0 else "main"
    head = args[1] if len(args) > 1 else "HEAD"

    print(bold(f"  Reviewing changes: {base} → {head}"))
    print()

    # Get diff first
    diff_data = _api_get(f"/git/diff?base={base}&head={head}")
    if diff_data:
        print(f"  Files changed: {diff_data.get('files_changed', 0)}")
        print(f"  +{diff_data.get('insertions', 0)} / -{diff_data.get('deletions', 0)}")
        print()

    # Send to code-reviewer agent with repo context
    cwd = _user_cwd()
    repo_name = os.path.basename(cwd)
    diff_text = diff_data.get("diff", "") if diff_data else ""
    prompt = (
        f"You are reviewing code in the project: {repo_name} (at {cwd}).\n"
        f"Review this code diff between {base} and {head}. "
        f"Identify bugs, security issues, and improvements:\n\n{diff_text[:10000]}"
    )

    body = {
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "cwd": cwd,
    }
    print(dim("  Sending to code-reviewer agent..."))
    result = _api_post("/v1/agents/code-reviewer/chat/completions", body)
    if result:
        choices = result.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            print()
            print(content)
    else:
        print(yellow("  Could not reach code-reviewer. Is the server running?"))
    print()


def cmd_pipeline(args: list[str]):
    """Manage CI/CD pipeline."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    sub = args[0] if args else "status"

    if sub == "start":
        branch = args[1] if len(args) > 1 else None
        if not branch:
            # Get current branch
            cur = _api_get("/git/current-branch")
            branch = cur.get("branch", "HEAD") if cur else "HEAD"

        print(bold(f"  Starting pipeline for branch: {cyan(branch)}"))
        data = _api_post("/pipeline/start", {"branch": branch})
        if data:
            print(green(f"  ✓ Pipeline started: run_id={data.get('run_id')}"))
            print(f"    Step: {data.get('current_step_name', '?')}")
            print(f"    Track: code-agents pipeline status {data.get('run_id')}")
        print()

    elif sub == "status":
        run_id = args[1] if len(args) > 1 else None
        if run_id:
            data = _api_get(f"/pipeline/{run_id}/status")
            if data:
                _print_pipeline_status(data)
            else:
                print(red(f"  Pipeline run {run_id} not found"))
        else:
            data = _api_get("/pipeline/runs")
            if data and data.get("runs"):
                for run in data["runs"]:
                    _print_pipeline_status(run)
                    print()
            else:
                print(dim("  No pipeline runs. Start one: code-agents pipeline start"))
        print()

    elif sub == "advance":
        run_id = args[1] if len(args) > 1 else None
        if not run_id:
            print(red("  Usage: code-agents pipeline advance <run_id>"))
            return
        data = _api_post(f"/pipeline/{run_id}/advance")
        if data:
            print(green(f"  ✓ Advanced to step {data.get('current_step')}: {data.get('current_step_name')}"))
        print()

    elif sub == "rollback":
        run_id = args[1] if len(args) > 1 else None
        if not run_id:
            print(red("  Usage: code-agents pipeline rollback <run_id>"))
            return
        data = _api_post(f"/pipeline/{run_id}/rollback")
        if data:
            print(yellow(f"  ⟲ Rollback triggered for pipeline {run_id}"))
            if data.get("rollback_info"):
                print(f"    {data['rollback_info'].get('instruction', '')}")
        print()

    else:
        print(f"  Unknown pipeline command: {sub}")
        print(f"  Usage: code-agents pipeline [start|status|advance|rollback] [args]")
        print()


def _print_pipeline_status(data: dict):
    """Pretty-print a pipeline run status."""
    bold, green, yellow, red, cyan, dim = _colors()

    status_icons = {
        "pending": "·", "in_progress": "▶", "success": "✓",
        "failed": "✗", "skipped": "○", "rolled_back": "⟲",
    }
    status_colors = {
        "pending": dim, "in_progress": cyan, "success": green,
        "failed": red, "skipped": dim, "rolled_back": yellow,
    }

    print(bold(f"  Pipeline: {data.get('run_id')}"))
    print(f"  Branch:   {cyan(data.get('branch', '?'))}")
    print(f"  Step:     {data.get('current_step')}/6 ({data.get('current_step_name', '?')})")
    if data.get("build_number"):
        print(f"  Build:    #{data['build_number']}")
    if data.get("error"):
        print(f"  Error:    {red(data['error'])}")
    print()

    steps = data.get("steps", {})
    for i in range(1, 7):
        step = steps.get(str(i), {})
        status = step.get("status", "pending")
        name = step.get("name", "?")
        icon = status_icons.get(status, "?")
        color_fn = status_colors.get(status, dim)
        print(f"    {color_fn(icon)} {i}. {name:<20} {color_fn(status)}")


def cmd_version():
    """Show version info."""
    bold, green, _, _, cyan, dim = _colors()
    try:
        import importlib.metadata
        version = importlib.metadata.version("code-agents")
    except Exception:
        version = "dev"

    print()
    print(f"  code-agents {bold(version)}")
    print(f"  Python {sys.version.split()[0]}")
    print(f"  Install: {dim(str(_find_code_agents_home()))}")
    print()


def cmd_curls(args: list[str] | None = None):
    """Show curl commands. Optionally filter by category or agent name."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    url = _server_url()
    args = args or []
    filter_key = args[0].lower() if args else None

    # Available categories
    categories = [
        "health", "agents", "git", "testing", "jenkins",
        "argocd", "pipeline", "redash", "elasticsearch",
    ]

    # If filter is an agent name, show curls for that agent
    if filter_key and filter_key not in categories:
        _curls_for_agent(filter_key, url)
        return

    # Show category index if no filter
    if not filter_key:
        print()
        print(bold(cyan("  ╔══════════════════════════════════════════════╗")))
        print(bold(cyan("  ║     Code Agents — API Curl Reference         ║")))
        print(bold(cyan("  ╚══════════════════════════════════════════════╝")))
        print()
        print(bold("  Filter by category:"))
        print(f"    code-agents curls {cyan('health')}         {dim('# health & diagnostics')}")
        print(f"    code-agents curls {cyan('agents')}         {dim('# agent listing & prompts')}")
        print(f"    code-agents curls {cyan('git')}            {dim('# git operations')}")
        print(f"    code-agents curls {cyan('testing')}        {dim('# test execution & coverage')}")
        print(f"    code-agents curls {cyan('jenkins')}        {dim('# Jenkins CI/CD')}")
        print(f"    code-agents curls {cyan('argocd')}         {dim('# ArgoCD deployment')}")
        print(f"    code-agents curls {cyan('pipeline')}       {dim('# CI/CD pipeline')}")
        print(f"    code-agents curls {cyan('redash')}         {dim('# database queries')}")
        print(f"    code-agents curls {cyan('elasticsearch')}  {dim('# search')}")
        print()
        print(bold("  Filter by agent name:"))
        print(f"    code-agents curls {cyan('code-reviewer')}  {dim('# curls for code-reviewer agent')}")
        print(f"    code-agents curls {cyan('git-ops')}        {dim('# curls for git-ops agent')}")
        print(f"    code-agents curls {cyan('<agent-name>')}   {dim('# curls for any agent')}")
        print()

        # List all agents
        try:
            from .config import agent_loader
            agent_loader.load()
            agents = agent_loader.list_agents()
            print(bold("  Available agents:"))
            for a in agents:
                print(f"    {cyan(a.name):<28} {dim(a.display_name or '')}")
        except Exception:
            pass
        print()
        return

    # Filtered output — show only the requested category
    _print_curl_sections(url, filter_key)


def _print_curl_sections(url: str, filt: str | None):
    """Print curl sections, optionally filtered to one category."""
    bold, green, yellow, red, cyan, dim = _colors()

    def section(name: str, key: str):
        """Return True if this section should be printed."""
        return filt is None or filt == key

    if section("Health & Diagnostics", "health"):
        print()
        print(bold("  Health & Diagnostics"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# Health check')}")
        print(f"  curl -s {url}/health | python3 -m json.tool")
        print()
        print(f"  {dim('# Full diagnostics (no secrets)')}")
        print(f"  curl -s {url}/diagnostics | python3 -m json.tool")

    if section("Agents", "agents"):
        print()
        print(bold("  Agents"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# List all agents')}")
        print(f"  curl -s {url}/v1/agents | python3 -m json.tool")
        print()
        print(f"  {dim('# List models (OpenAI-compatible)')}")
        print(f"  curl -s {url}/v1/models | python3 -m json.tool")
        print()
        print(f"  {dim('# Send a prompt (non-streaming)')}")
        print(f"  curl -s -X POST {url}/v1/agents/code-reasoning/chat/completions \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"Explain this project\"}}]}}' \\")
        print(f"    | python3 -m json.tool")
        print()
        print(f"  {dim('# Send a prompt (streaming)')}")
        print(f"  curl -N -X POST {url}/v1/agents/code-reasoning/chat/completions \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"What files are here?\"}}], \"stream\": true}}'")
        print()
        print(dim("  Tip: code-agents curls <agent-name>  for agent-specific curls"))

    if section("Git Operations", "git"):
        print()
        print(bold("  Git Operations"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# List branches')}")
        print(f"  curl -s {url}/git/branches | python3 -m json.tool")
        print()
        print(f"  {dim('# Current branch')}")
        print(f"  curl -s {url}/git/current-branch | python3 -m json.tool")
        print()
        print(f"  {dim('# Diff between branches')}")
        print(f"  curl -s '{url}/git/diff?base=main&head=HEAD' | python3 -m json.tool")
        print()
        print(f"  {dim('# Commit log')}")
        print(f"  curl -s '{url}/git/log?branch=main&limit=10' | python3 -m json.tool")
        print()
        print(f"  {dim('# Working tree status')}")
        print(f"  curl -s {url}/git/status | python3 -m json.tool")
        print()
        print(f"  {dim('# Push a branch')}")
        print(f"  curl -s -X POST {url}/git/push \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"branch\": \"feature-123\", \"remote\": \"origin\"}}' \\")
        print(f"    | python3 -m json.tool")
        print()
        print(f"  {dim('# Fetch from remote')}")
        print(f"  curl -s -X POST '{url}/git/fetch?remote=origin' | python3 -m json.tool")

    if section("Testing & Coverage", "testing"):
        print()
        print(bold("  Testing & Coverage"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# Run tests')}")
        print(f"  curl -s -X POST {url}/testing/run \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Run tests on a specific branch')}")
        print(f"  curl -s -X POST {url}/testing/run \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"branch\": \"feature-123\"}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Get coverage report')}")
        print(f"  curl -s {url}/testing/coverage | python3 -m json.tool")
        print()
        print(f"  {dim('# Coverage gaps (new code without tests)')}")
        print(f"  curl -s '{url}/testing/gaps?base=main&head=HEAD' | python3 -m json.tool")

    if section("Jenkins CI/CD", "jenkins"):
        print()
        print(bold("  Jenkins CI/CD"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# Trigger a build')}")
        print(f"  curl -s -X POST {url}/jenkins/build \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"job_name\": \"my-project\", \"branch\": \"feature-123\"}}' \\")
        print(f"    | python3 -m json.tool")
        print()
        print(f"  {dim('# Check build status')}")
        print(f"  curl -s {url}/jenkins/build/my-project/42/status | python3 -m json.tool")
        print()
        print(f"  {dim('# Get build console log')}")
        print(f"  curl -s {url}/jenkins/build/my-project/42/log | python3 -m json.tool")
        print()
        print(f"  {dim('# Wait for build to finish')}")
        print(f"  curl -s -X POST {url}/jenkins/build/my-project/42/wait | python3 -m json.tool")
        print()
        print(f"  {dim('# Last build info')}")
        print(f"  curl -s {url}/jenkins/build/my-project/last | python3 -m json.tool")

    if section("ArgoCD", "argocd"):
        print()
        print(bold("  ArgoCD"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# App sync & health status')}")
        print(f"  curl -s {url}/argocd/apps/my-app/status | python3 -m json.tool")
        print()
        print(f"  {dim('# List pods with image tags')}")
        print(f"  curl -s {url}/argocd/apps/my-app/pods | python3 -m json.tool")
        print()
        print(f"  {dim('# Get pod logs (scan for errors)')}")
        print(f"  curl -s '{url}/argocd/apps/my-app/pods/my-pod-abc/logs?namespace=default&tail=200' \\")
        print(f"    | python3 -m json.tool")
        print()
        print(f"  {dim('# Trigger sync')}")
        print(f"  curl -s -X POST {url}/argocd/apps/my-app/sync \\")
        print(f"    -H 'Content-Type: application/json' -d '{{}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Rollback to previous revision')}")
        print(f"  curl -s -X POST {url}/argocd/apps/my-app/rollback \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"revision\": \"previous\"}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Deployment history')}")
        print(f"  curl -s {url}/argocd/apps/my-app/history | python3 -m json.tool")
        print()
        print(f"  {dim('# Wait for sync to complete')}")
        print(f"  curl -s -X POST {url}/argocd/apps/my-app/wait-sync | python3 -m json.tool")

    if section("CI/CD Pipeline", "pipeline"):
        print()
        print(bold("  CI/CD Pipeline"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# Start a pipeline run')}")
        print(f"  curl -s -X POST {url}/pipeline/start \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"branch\": \"feature-123\"}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Check pipeline status')}")
        print(f"  curl -s {url}/pipeline/RUN_ID/status | python3 -m json.tool")
        print()
        print(f"  {dim('# Advance to next step')}")
        print(f"  curl -s -X POST {url}/pipeline/RUN_ID/advance \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"details\": {{\"build_number\": 42}}}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Mark step as failed')}")
        print(f"  curl -s -X POST {url}/pipeline/RUN_ID/fail \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"error\": \"Build failed\"}}' | python3 -m json.tool")
        print()
        print(f"  {dim('# Trigger rollback')}")
        print(f"  curl -s -X POST {url}/pipeline/RUN_ID/rollback | python3 -m json.tool")
        print()
        print(f"  {dim('# List all pipeline runs')}")
        print(f"  curl -s {url}/pipeline/runs | python3 -m json.tool")

    if section("Redash", "redash"):
        print()
        print(bold("  Redash (Database Queries)"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# List data sources')}")
        print(f"  curl -s {url}/redash/data-sources | python3 -m json.tool")
        print()
        print(f"  {dim('# Get table schema')}")
        print(f"  curl -s {url}/redash/data-sources/1/schema | python3 -m json.tool")
        print()
        print(f"  {dim('# Run a SQL query')}")
        print(f"  curl -s -X POST {url}/redash/run-query \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"data_source_id\": 1, \"query\": \"SELECT * FROM users LIMIT 10\"}}' \\")
        print(f"    | python3 -m json.tool")

    if section("Elasticsearch", "elasticsearch"):
        print()
        print(bold("  Elasticsearch"))
        print(bold("  " + "─" * 44))
        print()
        print(f"  {dim('# Cluster info')}")
        print(f"  curl -s {url}/elasticsearch/info | python3 -m json.tool")
        print()
        print(f"  {dim('# Search')}")
        print(f"  curl -s -X POST {url}/elasticsearch/search \\")
        print(f"    -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"index\": \"*\", \"body\": {{\"query\": {{\"match_all\": {{}}}}, \"size\": 10}}}}' \\")
        print(f"    | python3 -m json.tool")

    print()
    if filt:
        print(dim(f"  Showing: {filt} | Run 'code-agents curls' for all categories"))
    else:
        print(dim(f"  Replace 'my-app', 'my-project', 'RUN_ID', etc. with your actual values."))
        print(dim(f"  Server URL: {url} (from HOST/PORT in .env)"))
    print()


def _curls_for_agent(agent_name: str, url: str):
    """Show curl commands specific to one agent."""
    bold, green, yellow, red, cyan, dim = _colors()

    # Verify agent exists
    agent_info = None
    try:
        from .config import agent_loader
        agent_loader.load()
        agent_info = agent_loader.get(agent_name)
    except Exception:
        pass

    if not agent_info:
        print()
        print(red(f"  Agent '{agent_name}' not found."))
        print()
        print(bold("  Available agents:"))
        try:
            for a in agent_loader.list_agents():
                print(f"    {cyan(a.name):<28} {dim(a.display_name or '')}")
        except Exception:
            pass
        print()
        return

    name = agent_info.name
    display = agent_info.display_name or name
    endpoint = f"{url}/v1/agents/{name}/chat/completions"

    print()
    print(bold(f"  Curls for: {cyan(display)} ({name})"))
    print(bold("  " + "─" * 44))
    print()
    print(f"  {dim('Endpoint:')} {endpoint}")
    print(f"  {dim('Backend:')}  {agent_info.backend}  {dim('Model:')} {agent_info.model}  {dim('Permission:')} {agent_info.permission_mode}")
    print()

    # Non-streaming prompt
    print(f"  {dim('# Send a prompt (non-streaming)')}")
    print(f"  curl -s -X POST {endpoint} \\")
    print(f"    -H 'Content-Type: application/json' \\")
    print(f"    -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"YOUR PROMPT HERE\"}}]}}' \\")
    print(f"    | python3 -m json.tool")
    print()

    # Streaming prompt
    print(f"  {dim('# Send a prompt (streaming)')}")
    print(f"  curl -N -X POST {endpoint} \\")
    print(f"    -H 'Content-Type: application/json' \\")
    print(f"    -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"YOUR PROMPT HERE\"}}], \"stream\": true}}'")
    print()

    # With session (multi-turn)
    print(f"  {dim('# Resume a session (multi-turn)')}")
    print(f"  curl -s -X POST {endpoint} \\")
    print(f"    -H 'Content-Type: application/json' \\")
    print(f"    -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"Follow up question\"}}], \"session_id\": \"SESSION_ID\"}}' \\")
    print(f"    | python3 -m json.tool")
    print()

    # Agent-specific example prompts
    _AGENT_EXAMPLES: dict[str, list[tuple[str, str]]] = {
        "code-reasoning": [
            ("Explain the architecture", "Explain the architecture of this project"),
            ("Trace a data flow", "Trace how a user request flows through the API"),
        ],
        "code-writer": [
            ("Write a function", "Write a function that validates email addresses"),
            ("Refactor code", "Refactor the authentication module to use JWT"),
        ],
        "code-reviewer": [
            ("Review for bugs", "Review this code for bugs and security issues"),
            ("Review a PR", "Review the changes in the latest commit for quality"),
        ],
        "code-tester": [
            ("Write tests", "Write unit tests for the user authentication module"),
            ("Debug a failure", "Debug why the payment processing test is failing"),
        ],
        "redash-query": [
            ("Explore schema", "Show me the tables in the acquiring database"),
            ("Write SQL", "Write a query to find all failed transactions today"),
        ],
        "git-ops": [
            ("Show recent changes", "Show the last 5 commits on the current branch"),
            ("Compare branches", "What changed between main and this branch?"),
        ],
        "test-coverage": [
            ("Run tests", "Run the test suite and show coverage"),
            ("Find gaps", "What new code is missing test coverage?"),
        ],
        "jenkins-build": [
            ("Trigger build", "Trigger a build for the feature-123 branch"),
            ("Check status", "What's the status of the last build?"),
        ],
        "jenkins-deploy": [
            ("Deploy build", "Deploy build #42 to staging"),
            ("Check deploy", "Is the deployment job still running?"),
        ],
        "argocd-verify": [
            ("Check pods", "Are all pods healthy after the latest deployment?"),
            ("Scan logs", "Check pod logs for any errors or exceptions"),
        ],
        "pipeline-orchestrator": [
            ("Start pipeline", "Start the deployment pipeline for branch feature-123"),
            ("Pipeline status", "What step is the current pipeline on?"),
        ],
        "agent-router": [
            ("Route request", "I need to review code changes in a PR"),
            ("Pick agent", "Which agent should I use to run database queries?"),
        ],
    }

    examples = _AGENT_EXAMPLES.get(name, [])
    if examples:
        print(f"  {bold('Example prompts for this agent:')}")
        print()
        for label, prompt_text in examples:
            print(f"  {dim(f'# {label}')}")
            print(f"  curl -s -X POST {endpoint} \\")
            print(f"    -H 'Content-Type: application/json' \\")
            print(f"    -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"{prompt_text}\"}}]}}' \\")
            print(f"    | python3 -m json.tool")
            print()

    print(dim(f"  Run 'code-agents curls' for all API categories"))
    print()


# ============================================================================
# MAIN DISPATCHER
# ============================================================================


COMMANDS = {
    "init":      ("Initialize code-agents in current repo",        cmd_init),
    "migrate":   ("Migrate legacy .env to centralized config",     cmd_migrate),
    "rules":     ("Manage rules [list|create|edit|delete]",        None),  # special handling
    "start":     ("Start the server",                               cmd_start),
    "restart":   ("Restart the server (shutdown + start)",          cmd_restart),
    "chat":      ("Interactive chat with agents",                   None),  # special handling
    "shutdown":  ("Shutdown the server",                              cmd_shutdown),
    "status":    ("Check server health and config",                 cmd_status),
    "agents":    ("List all available agents",                      cmd_agents),
    "config":    ("Show current .env configuration",                cmd_config),
    "doctor":    ("Diagnose common issues",                         cmd_doctor),
    "logs":      ("Tail the log file",                              None),  # special handling
    "diff":      ("Show git diff between branches",                 None),
    "branches":  ("List git branches",                              cmd_branches),
    "test":      ("Run tests on the target repo",                   None),
    "review":    ("Review code changes with AI",                    None),
    "pipeline":  ("Manage CI/CD pipeline [start|status|advance|rollback]", None),
    "setup":     ("Full interactive setup wizard",                  None),
    "curls":     ("Show all API curl commands",                     cmd_curls),
    "version":   ("Show version info",                              cmd_version),
    "completions": ("Generate shell completion script",             None),  # special handling
}

# Subcommands for commands that take them
_SUBCOMMANDS = {
    "rules":    ["list", "create", "edit", "delete"],
    "pipeline": ["start", "status", "advance", "rollback"],
    "start":    ["--fg", "--foreground"],
    "rules create": ["--global", "--agent"],
    "rules list": ["--agent"],
    "chat":     list(AGENT_ROLES.keys()) if "AGENT_ROLES" in dir() else [],
}

# Agent names for chat completion
try:
    from .chat import AGENT_ROLES as _AGENT_ROLES
    _SUBCOMMANDS["chat"] = list(_AGENT_ROLES.keys())
except Exception:
    pass


def _generate_zsh_completion() -> str:
    """Generate zsh completion script for code-agents."""
    cmds = sorted(COMMANDS.keys())
    cmd_list = " ".join(cmds) + " help"
    agents = " ".join(sorted(AGENT_ROLES.keys())) if "AGENT_ROLES" in dir() else ""

    return f'''#compdef code-agents
# Zsh completion for code-agents CLI
# Install: code-agents completions --zsh >> ~/.zshrc

_code_agents() {{
    local -a commands
    commands=(
        'init:Initialize code-agents in current repo'
        'migrate:Migrate legacy .env to centralized config'
        'rules:Manage agent rules (list/create/edit/delete)'
        'start:Start the server'
        'restart:Restart the server'
        'chat:Interactive chat with agents'
        'shutdown:Shutdown the server'
        'status:Check server health and config'
        'agents:List all available agents'
        'config:Show current configuration'
        'doctor:Diagnose common issues'
        'logs:Tail the log file'
        'diff:Show git diff between branches'
        'branches:List git branches'
        'test:Run tests on the target repo'
        'review:Review code changes with AI'
        'pipeline:Manage CI/CD pipeline'
        'setup:Full interactive setup wizard'
        'curls:Show API curl commands'
        'version:Show version info'
        'help:Show help'
        'completions:Generate shell completion script'
    )

    local -a rules_subcmds
    rules_subcmds=('list:List active rules' 'create:Create a new rule' 'edit:Edit a rule file' 'delete:Delete a rule file')

    local -a pipeline_subcmds
    pipeline_subcmds=('start:Start pipeline' 'status:Show pipeline status' 'advance:Advance pipeline step' 'rollback:Rollback deployment')

    local -a agents
    agents=({agents})

    if (( CURRENT == 2 )); then
        _describe 'command' commands
    elif (( CURRENT == 3 )); then
        case $words[2] in
            rules)
                _describe 'subcommand' rules_subcmds
                ;;
            pipeline)
                _describe 'subcommand' pipeline_subcmds
                ;;
            chat)
                _values 'agent' $agents
                ;;
            start)
                _values 'flag' '--fg' '--foreground'
                ;;
        esac
    elif (( CURRENT == 4 )); then
        case "$words[2] $words[3]" in
            "rules create"|"rules list")
                _values 'flag' '--global' '--agent'
                ;;
        esac
    elif (( CURRENT == 5 )); then
        case "$words[4]" in
            --agent)
                _values 'agent' $agents
                ;;
        esac
    fi
}}

compdef _code_agents code-agents
'''


def _generate_bash_completion() -> str:
    """Generate bash completion script for code-agents."""
    cmds = sorted(COMMANDS.keys())
    cmd_list = " ".join(cmds) + " help completions"

    return f'''# Bash completion for code-agents CLI
# Install: code-agents completions --bash >> ~/.bashrc

_code_agents_completions() {{
    local cur prev commands
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    commands="{cmd_list}"

    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
    elif [[ $COMP_CWORD -eq 2 ]]; then
        case "$prev" in
            rules)
                COMPREPLY=( $(compgen -W "list create edit delete" -- "$cur") )
                ;;
            pipeline)
                COMPREPLY=( $(compgen -W "start status advance rollback" -- "$cur") )
                ;;
            chat)
                COMPREPLY=( $(compgen -W "agent-router argocd-verify code-reasoning code-reviewer code-tester code-writer git-ops jenkins-build jenkins-deploy pipeline-orchestrator redash-query test-coverage" -- "$cur") )
                ;;
            start)
                COMPREPLY=( $(compgen -W "--fg --foreground" -- "$cur") )
                ;;
        esac
    elif [[ $COMP_CWORD -eq 3 ]]; then
        case "${{COMP_WORDS[1]}} ${{COMP_WORDS[2]}}" in
            "rules create"|"rules list")
                COMPREPLY=( $(compgen -W "--global --agent" -- "$cur") )
                ;;
        esac
    elif [[ $COMP_CWORD -eq 4 ]] && [[ "$prev" == "--agent" ]]; then
        COMPREPLY=( $(compgen -W "agent-router argocd-verify code-reasoning code-reviewer code-tester code-writer git-ops jenkins-build jenkins-deploy pipeline-orchestrator redash-query test-coverage" -- "$cur") )
    fi
}}

complete -F _code_agents_completions code-agents
'''


def cmd_completions(rest: list[str] | None = None):
    """Generate shell completion script."""
    rest = rest or []
    bold, green, yellow, red, cyan, dim = _colors()

    if "--zsh" in rest:
        print(_generate_zsh_completion())
    elif "--bash" in rest:
        print(_generate_bash_completion())
    elif "--install" in rest:
        # Auto-detect shell and install
        shell_rc = None
        if os.path.exists(os.path.expanduser("~/.zshrc")):
            shell_rc = os.path.expanduser("~/.zshrc")
            script = _generate_zsh_completion()
            marker = "# code-agents completion"
        elif os.path.exists(os.path.expanduser("~/.bashrc")):
            shell_rc = os.path.expanduser("~/.bashrc")
            script = _generate_bash_completion()
            marker = "# code-agents completion"
        else:
            print(red("  Could not detect shell config (~/.zshrc or ~/.bashrc)"))
            return

        # Check if already installed
        with open(shell_rc) as f:
            if marker in f.read():
                print(green(f"  ✓ Completions already installed in {shell_rc}"))
                return

        with open(shell_rc, "a") as f:
            f.write(f"\n{marker}\n")
            f.write(script)
            f.write(f"\n")

        print(green(f"  ✓ Completions installed in {shell_rc}"))
        print(dim(f"    Restart your terminal or run: source {shell_rc}"))
    else:
        print()
        print(bold("  Generate shell completion for code-agents"))
        print()
        print(f"    {cyan('code-agents completions --install')}    {dim('Auto-install to ~/.zshrc or ~/.bashrc')}")
        print(f"    {cyan('code-agents completions --zsh')}        {dim('Print zsh completion script')}")
        print(f"    {cyan('code-agents completions --bash')}       {dim('Print bash completion script')}")
        print()


def cmd_help():
    """Show comprehensive help with all commands, args, and examples."""
    bold, green, yellow, red, cyan, dim = _colors()
    p = print  # shorthand

    p()
    p(bold("  code-agents — AI-powered code agent platform"))
    p(bold("  " + "─" * 50))
    p()
    p(bold("  USAGE:"))
    p(f"    code-agents {cyan('<command>')} [args] [options]")
    p()

    # ── Getting Started ──
    p(bold("  GETTING STARTED"))
    p()
    p(f"    {cyan('init')}")
    p(f"      Initialize code-agents in the current repo directory.")
    p(f"      Prompts for API keys, server config, Jenkins/ArgoCD settings.")
    p(f"      Global config → ~/.code-agents/config.env")
    p(f"      Per-repo config → .env.code-agents")
    p(f"      {dim('$ cd /path/to/your-project')}")
    p(f"      {dim('$ code-agents init')}")
    p()
    p(f"    {cyan('migrate')}")
    p(f"      Migrate a legacy .env file to centralized config.")
    p(f"      Splits variables: API keys → global, Jenkins/ArgoCD → per-repo.")
    p(f"      Backs up the original .env file.")
    p(f"      {dim('$ code-agents migrate')}")
    p()
    p(f"    {cyan('rules')} {dim('[list|create|edit|delete]')}")
    p(f"      Manage agent rules — persistent instructions injected into prompts.")
    p(f"      Rules auto-refresh: edit a file mid-chat and the next message picks it up.")
    p(f"        {dim('list')}                 List active rules (default)")
    p(f"        {dim('list --agent X')}       List rules for a specific agent")
    p(f"        {dim('create')}               Create project rule for all agents")
    p(f"        {dim('create --agent X')}     Create project rule for specific agent")
    p(f"        {dim('create --global')}      Create global rule for all agents")
    p(f"        {dim('edit <path>')}          Edit a rule file in $EDITOR")
    p(f"        {dim('delete <path>')}        Delete a rule file")
    p(f"      {dim('$ code-agents rules')}")
    p(f"      {dim('$ code-agents rules create --agent code-writer')}")
    p()
    p(f"    {cyan('start')} {dim('[--fg]')}")
    p(f"      Start the server in background. Loads global + per-repo config.")
    p(f"      Shows URLs, PID, and curl commands when started.")
    p(f"        {dim('--fg')}    Run in foreground (shows logs, Ctrl+C to stop)")
    p(f"      {dim('$ code-agents start')}")
    p(f"      {dim('$ code-agents start --fg')}")
    p()
    p(f"    {cyan('restart')}")
    p(f"      Restart the server (shutdown + start).")
    p(f"      Stops the running server, then starts a new one.")
    p(f"      {dim('$ code-agents restart')}")
    p()
    p(f"    {cyan('chat')} {dim('[agent-name]')}")
    p(f"      Open interactive chat REPL. If no agent specified, shows a")
    p(f"      numbered menu to pick from all 12 agents. Each agent stays")
    p(f"      in its role (writer writes code, tester writes tests, etc.).")
    p(f"      Supports multi-turn sessions, streaming responses, and agent switching.")
    p(f"        {dim('<agent-name>')}  Skip menu, start directly with this agent")
    p(f"      {dim('$ code-agents chat                  # pick from menu')}")
    p(f"      {dim('$ code-agents chat code-reasoning   # start with reasoning')}")
    p(f"      {dim('$ code-agents chat code-writer      # start with writer')}")
    p(f"      {dim('$ code-agents chat code-tester      # start with tester')}")
    p()
    p(f"      {bold('Chat slash commands (inside the chat):')}")
    p(f"        {cyan('/help'):<18} Show all chat commands")
    p(f"        {cyan('/quit'):<18} Exit the chat (also: /exit, /q, or Ctrl+C)")
    p(f"        {cyan('/agent <name>'):<18} Switch to another agent (clears session)")
    p(f"                           Examples: /agent code-writer, /agent code-tester")
    p(f"        {cyan('/agents'):<18} List all 12 agents with roles, mark current")
    p(f"        {cyan('/rules'):<18} Show active rules for the current agent")
    p(f"        {cyan('/run <cmd>'):<18} Run a shell command in the repo directory")
    p(f"        {cyan('/session'):<18} Show current session ID (for multi-turn context)")
    p(f"        {cyan('/clear'):<18} Clear session — next message starts fresh")
    p(f"        {cyan('/<agent> <prompt>'):<18} Delegate a one-shot prompt to another agent")
    p()
    p(f"      {bold('Agent Rules (persistent instructions):')}")
    p(f"        Rules are markdown files injected into agent system prompts.")
    p(f"        Global: ~/.code-agents/rules/  |  Project: .code-agents/rules/")
    p(f"        _global.md → all agents  |  code-writer.md → specific agent")
    p(f"        Auto-refresh: edit mid-chat, next message picks it up.")
    p(f"        {dim('$ code-agents rules                      # list active rules')}")
    p(f"        {dim('$ code-agents rules create --agent X     # create for specific agent')}")
    p(f"        {dim('$ code-agents rules create --global      # create global rule')}")
    p()
    p(f"      {bold('Available agents for chat:')}")
    p(f"        code-reasoning       {dim('Explain architecture, trace flows (read-only)')}")
    p(f"        code-writer          {dim('Write/modify code, refactor, implement features')}")
    p(f"        code-reviewer        {dim('Review for bugs, security, style violations')}")
    p(f"        code-tester          {dim('Write tests, debug, optimize code quality')}")
    p(f"        redash-query         {dim('SQL queries, explore database schemas')}")
    p(f"        git-ops              {dim('Git branches, diffs, logs, push')}")
    p(f"        test-coverage        {dim('Run tests, coverage reports, find gaps')}")
    p(f"        jenkins-build        {dim('Trigger/monitor Jenkins CI builds')}")
    p(f"        jenkins-deploy       {dim('Trigger/monitor Jenkins deployments')}")
    p(f"        argocd-verify        {dim('Check pods, scan logs, rollback deployments')}")
    p(f"        pipeline-orchestrator {dim('Guide full CI/CD pipeline end-to-end')}")
    p(f"        agent-router         {dim('Help pick the right specialist agent')}")
    p()
    p(f"    {cyan('setup')}")
    p(f"      Full interactive setup wizard (7 steps). Same as code-agents-setup.")
    p(f"      Checks Python, installs deps, prompts for all keys, writes .env.")
    p(f"      {dim('$ code-agents setup')}")
    p()

    # ── Server ──
    p(bold("  SERVER MANAGEMENT"))
    p()
    p(f"    {cyan('shutdown')}")
    p(f"      Stop the running server. Finds and kills the process on the")
    p(f"      configured PORT (default 8000). Uses SIGTERM then SIGKILL.")
    p(f"      {dim('$ code-agents shutdown')}")
    p()
    p(f"    {cyan('status')}")
    p(f"      Check if the server is running. Shows health, version, agent count,")
    p(f"      integration status (Jenkins/ArgoCD/Elasticsearch), and curl commands.")
    p(f"      {dim('$ code-agents status')}")
    p()
    p(f"    {cyan('logs')} {dim('[lines]')}")
    p(f"      Tail the log file in real-time (Ctrl+C to stop).")
    p(f"      Log file: logs/code-agents.log (hourly rotation, 7-day retention).")
    p(f"        {dim('<lines>')}  Number of lines to show (default: 50)")
    p(f"      {dim('$ code-agents logs           # last 50 lines, live')}")
    p(f"      {dim('$ code-agents logs 200       # last 200 lines, live')}")
    p()
    p(f"    {cyan('config')}")
    p(f"      Show current .env configuration from the current directory.")
    p(f"      Groups by category (Core, Server, Jenkins, ArgoCD, etc.).")
    p(f"      Secrets are masked (shows first/last 4 chars only).")
    p(f"      {dim('$ code-agents config')}")
    p()
    p(f"    {cyan('doctor')}")
    p(f"      Diagnose common issues. Checks: Python version, .env file,")
    p(f"      API keys, cursor-agent-sdk, server running, Jenkins/ArgoCD config,")
    p(f"      git repo, log directory. Reports issues with fix suggestions.")
    p(f"      {dim('$ code-agents doctor')}")
    p()

    # ── Git ──
    p(bold("  GIT OPERATIONS"))
    p()
    p(f"    {cyan('branches')}")
    p(f"      List all git branches. Highlights the current branch.")
    p(f"      Works with or without the server running (falls back to git).")
    p(f"      {dim('$ code-agents branches')}")
    p()
    p(f"    {cyan('diff')} {dim('[base] [head]')}")
    p(f"      Show diff between two branches with file-level stats.")
    p(f"        {dim('<base>')}  Base branch (default: main)")
    p(f"        {dim('<head>')}  Head branch (default: HEAD)")
    p(f"      {dim('$ code-agents diff                    # main vs HEAD')}")
    p(f"      {dim('$ code-agents diff main feature-123   # main vs feature-123')}")
    p(f"      {dim('$ code-agents diff develop HEAD       # develop vs HEAD')}")
    p()

    # ── CI/CD ──
    p(bold("  CI/CD & TESTING"))
    p()
    p(f"    {cyan('test')} {dim('[branch]')}")
    p(f"      Run tests on the target repository. Auto-detects test framework")
    p(f"      (pytest, jest, maven, gradle, go). Shows pass/fail/error counts.")
    p(f"        {dim('<branch>')}  Checkout this branch before running (optional)")
    p(f"      {dim('$ code-agents test                    # test current branch')}")
    p(f"      {dim('$ code-agents test feature-123        # test specific branch')}")
    p()
    p(f"    {cyan('review')} {dim('[base] [head]')}")
    p(f"      AI-powered code review. Gets the diff between branches and sends")
    p(f"      it to the code-reviewer agent for bug/security/style analysis.")
    p(f"        {dim('<base>')}  Base branch (default: main)")
    p(f"        {dim('<head>')}  Head branch (default: HEAD)")
    p(f"      {dim('$ code-agents review                  # review HEAD vs main')}")
    p(f"      {dim('$ code-agents review main feature-123 # review specific range')}")
    p()
    p(f"    {cyan('pipeline')} {dim('<subcommand> [args]')}")
    p(f"      Manage the 6-step CI/CD pipeline:")
    p(f"      connect → review/test → build → deploy → verify → rollback")
    p()
    p(f"      {cyan('pipeline start')} {dim('[branch]')}")
    p(f"        Start a new pipeline run. Uses current branch if not specified.")
    p(f"        {dim('$ code-agents pipeline start')}")
    p(f"        {dim('$ code-agents pipeline start feature-123')}")
    p()
    p(f"      {cyan('pipeline status')} {dim('[run_id]')}")
    p(f"        Show pipeline status. Without run_id, lists all runs.")
    p(f"        {dim('$ code-agents pipeline status')}")
    p(f"        {dim('$ code-agents pipeline status abc123')}")
    p()
    p(f"      {cyan('pipeline advance')} {dim('<run_id>')}")
    p(f"        Mark current step as done and advance to the next step.")
    p(f"        {dim('$ code-agents pipeline advance abc123')}")
    p()
    p(f"      {cyan('pipeline rollback')} {dim('<run_id>')}")
    p(f"        Trigger rollback. Skips remaining steps, jumps to step 6.")
    p(f"        {dim('$ code-agents pipeline rollback abc123')}")
    p()

    # ── Other ──
    p(bold("  INFORMATION"))
    p()
    p(f"    {cyan('agents')}")
    p(f"      List all 12 available agents with backend, model, and permissions.")
    p(f"      Works with or without the server running.")
    p(f"      {dim('$ code-agents agents')}")
    p()
    p(f"    {cyan('curls')} {dim('[category | agent-name]')}")
    p(f"      Show copy-pasteable curl commands for all API endpoints.")
    p(f"      Without args: shows category index + agent list.")
    p(f"      With category: shows curls for that category only.")
    p(f"      With agent name: shows agent-specific curls + example prompts.")
    p(f"        Categories: health, agents, git, testing, jenkins, argocd,")
    p(f"                    pipeline, redash, elasticsearch")
    p(f"      {dim('$ code-agents curls                   # show index')}")
    p(f"      {dim('$ code-agents curls jenkins           # jenkins curls only')}")
    p(f"      {dim('$ code-agents curls argocd            # argocd curls only')}")
    p(f"      {dim('$ code-agents curls code-reviewer     # curls for code-reviewer')}")
    p(f"      {dim('$ code-agents curls pipeline          # pipeline curls only')}")
    p()
    p(f"    {cyan('version')}")
    p(f"      Show version, Python version, and install location.")
    p(f"      {dim('$ code-agents version')}")
    p()
    p(f"    {cyan('help')}")
    p(f"      Show this help message with all commands and arguments.")
    p(f"      {dim('$ code-agents help')}")
    p()

    # ── Install ──
    p(bold("  INSTALLATION"))
    p()
    p(f"    {dim('# One-command install (from anywhere):')}")
    p(f"    curl -fsSL https://raw.githubusercontent.com/shivanshu1gupta-paytmpayments/code-agents/main/install.sh | bash")
    p()
    p(f"    {dim('# Then initialize in any project:')}")
    p(f"    cd /path/to/your-project")
    p(f"    code-agents init")
    p(f"    code-agents start")
    p(f"    code-agents chat")
    p()


def main():
    """CLI entry point — dispatches to subcommands."""
    args = sys.argv[1:]

    if not args:
        cmd_start()
        return

    command = args[0].lower()
    rest = args[1:]

    try:
        if command in ("--help", "-h", "help"):
            cmd_help()
        elif command in ("--version", "-v", "version"):
            cmd_version()
        elif command == "init":
            cmd_init()
        elif command == "start":
            cmd_start()
        elif command == "restart":
            cmd_restart()
        elif command == "chat":
            from .chat import chat_main
            chat_main(rest)
        elif command == "shutdown":
            cmd_shutdown()
        elif command == "status":
            cmd_status()
        elif command == "agents":
            cmd_agents()
        elif command == "config":
            cmd_config()
        elif command == "doctor":
            cmd_doctor()
        elif command == "logs":
            cmd_logs(rest)
        elif command == "diff":
            cmd_diff(rest)
        elif command == "branches":
            cmd_branches()
        elif command == "test":
            cmd_test(rest)
        elif command == "review":
            cmd_review(rest)
        elif command == "pipeline":
            cmd_pipeline(rest)
        elif command == "curls":
            cmd_curls(rest)
        elif command == "setup":
            from .setup import main as setup_main
            setup_main()
        elif command == "migrate":
            cmd_migrate()
        elif command == "rules":
            cmd_rules(rest)
        elif command == "completions":
            cmd_completions(rest)
        else:
            print(f"  Unknown command: {command}")
            print(f"  Run 'code-agents help' for usage.")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n  Cancelled.")
    except EOFError:
        print("\n  Cancelled.")


if __name__ == "__main__":
    main()
