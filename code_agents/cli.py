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


def _load_env():
    """Load .env from cwd if it exists."""
    env_file = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_file):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=True)
        except ImportError:
            pass
    os.environ.setdefault("TARGET_REPO_PATH", os.getcwd())


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

    cwd = os.getcwd()
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
    original_dir = os.getcwd()
    os.chdir(cwd)
    write_env_file(env_vars)
    os.chdir(original_dir)

    print()
    print(green(f"  ✓ Initialized in: {cwd}"))
    print(f"  .env written to: {cyan(os.path.join(cwd, '.env'))}")
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


def _start_background(repo_path: str):
    """Start the server in background and show a clean summary."""
    bold, green, yellow, red, cyan, dim = _colors()

    env_file = os.path.join(repo_path, ".env")
    if os.path.exists(env_file):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=True)
        except ImportError:
            pass

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


def cmd_start():
    """Start the server in background pointing at the current directory."""
    _load_env()
    cwd = os.getcwd()

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
        cwd = os.getcwd()
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
        print(f"  Repo:     {cyan(os.getenv('TARGET_REPO_PATH', os.getcwd()))}")
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

    cwd = os.getcwd()
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
    """Diagnose common issues."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()
    cwd = os.getcwd()
    issues = 0

    print()
    print(bold("  Code Agents Doctor"))
    print(bold("  " + "─" * 40))

    # Check .env
    env_file = os.path.join(cwd, ".env")
    if os.path.exists(env_file):
        print(green("  ✓ .env file found"))
    else:
        print(red("  ✗ No .env file — run: code-agents init"))
        issues += 1

    # Check Python
    import sys
    if sys.version_info >= (3, 10):
        print(green(f"  ✓ Python {sys.version_info.major}.{sys.version_info.minor}"))
    else:
        print(red(f"  ✗ Python {sys.version_info.major}.{sys.version_info.minor} — need 3.10+"))
        issues += 1

    # Check git repo
    if os.path.isdir(os.path.join(cwd, ".git")):
        print(green(f"  ✓ Git repo detected"))
    else:
        print(yellow("  ! Not a git repo (git-ops commands won't work)"))

    # Check API key
    if os.getenv("CURSOR_API_KEY") or os.getenv("ANTHROPIC_API_KEY"):
        print(green("  ✓ Backend API key configured"))
    else:
        print(red("  ✗ No CURSOR_API_KEY or ANTHROPIC_API_KEY — run: code-agents init"))
        issues += 1

    # Check cursor-agent-sdk
    try:
        import cursor_agent_sdk
        print(green("  ✓ cursor-agent-sdk installed"))
    except ImportError:
        print(yellow("  ! cursor-agent-sdk not installed (needed for Cursor backend)"))

    # Check server running
    data = _api_get("/health")
    if data and data.get("status") == "ok":
        print(green(f"  ✓ Server running at {_server_url()}"))
    else:
        print(yellow(f"  ! Server not running at {_server_url()}"))

    # Check logs directory
    log_dir = _find_code_agents_home() / "logs"
    if log_dir.exists():
        print(green(f"  ✓ Log directory exists"))
    else:
        print(yellow("  ! Log directory missing (will be created on server start)"))

    # Check Jenkins
    if os.getenv("JENKINS_URL"):
        if os.getenv("JENKINS_API_TOKEN"):
            print(green("  ✓ Jenkins configured"))
        else:
            print(red("  ✗ JENKINS_URL set but JENKINS_API_TOKEN missing"))
            issues += 1
    else:
        print(dim("  · Jenkins not configured (optional)"))

    # Check ArgoCD
    if os.getenv("ARGOCD_URL"):
        if os.getenv("ARGOCD_AUTH_TOKEN"):
            print(green("  ✓ ArgoCD configured"))
        else:
            print(red("  ✗ ARGOCD_URL set but ARGOCD_AUTH_TOKEN missing"))
            issues += 1
    else:
        print(dim("  · ArgoCD not configured (optional)"))

    print()
    if issues == 0:
        print(green(bold("  All checks passed!")))
    else:
        print(yellow(f"  {issues} issue(s) found — fix them and run 'code-agents doctor' again"))
    print()


def cmd_diff(args: list[str]):
    """Show git diff between branches."""
    bold, green, yellow, red, cyan, dim = _colors()
    _load_env()

    base = args[0] if len(args) > 0 else "main"
    head = args[1] if len(args) > 1 else "HEAD"

    data = _api_get(f"/git/diff?base={base}&head={head}")
    if not data:
        # Fallback: run git directly
        print(dim(f"  Server not running — using git directly"))
        import asyncio
        from .git_client import GitClient
        client = GitClient(os.getcwd())
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

    data = _api_get("/git/branches")
    if not data:
        import asyncio
        from .git_client import GitClient
        client = GitClient(os.getcwd())
        try:
            branches = asyncio.run(client.list_branches())
            data = {"branches": branches}
        except Exception as e:
            print(red(f"  Error: {e}"))
            return

    # Get current branch
    current = None
    cur_data = _api_get("/git/current-branch")
    if cur_data:
        current = cur_data.get("branch")
    else:
        import asyncio
        from .git_client import GitClient
        client = GitClient(os.getcwd())
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

    branch = args[0] if args else None
    body: dict = {}
    if branch:
        body["branch"] = branch

    print(bold("  Running tests..."))
    print()

    data = _api_post("/testing/run", body)
    if not data:
        # Fallback: run directly
        import asyncio
        from .testing_client import TestingClient
        client = TestingClient(os.getcwd())
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

    # Send to code-reviewer agent
    diff_text = diff_data.get("diff", "") if diff_data else ""
    prompt = f"Review this code diff between {base} and {head}. Identify bugs, security issues, and improvements:\n\n{diff_text[:10000]}"

    body = {
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
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
    "start":     ("Start the server",                               cmd_start),
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
}


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
    p(f"      Writes .env in the current directory. Offers to start server.")
    p(f"      {dim('$ cd /path/to/your-project')}")
    p(f"      {dim('$ code-agents init')}")
    p()
    p(f"    {cyan('start')} {dim('[--fg]')}")
    p(f"      Start the server in background. Reads .env from current directory.")
    p(f"      Shows URLs, PID, and curl commands when started.")
    p(f"        {dim('--fg')}    Run in foreground (shows logs, Ctrl+C to stop)")
    p(f"      {dim('$ code-agents start')}")
    p(f"      {dim('$ code-agents start --fg')}")
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
    p(f"        {cyan('/session'):<18} Show current session ID (for multi-turn context)")
    p(f"        {cyan('/clear'):<18} Clear session — next message starts fresh")
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
