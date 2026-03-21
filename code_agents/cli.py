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
    """Start the server pointing at the current directory."""
    _load_env()
    bold, green, _, _, cyan, dim = _colors()
    cwd = os.getcwd()

    # Check for --background / -bg flag
    if "--bg" in sys.argv or "--background" in sys.argv:
        _start_background(cwd)
        return

    host = os.getenv("HOST", "0.0.0.0")
    port = os.getenv("PORT", "8000")

    print()
    print(bold(cyan("  Starting Code Agents (foreground)...")))
    print(dim(f"  Target repo: {cwd}"))
    print(dim(f"  Server:      http://{host}:{port}"))
    print(dim(f"  Logs:        {_find_code_agents_home()}/logs/code-agents.log"))
    print(dim("  Press Ctrl+C to stop"))
    print(dim("  Tip: use 'code-agents start --bg' to run in background"))
    print()

    from .main import main as run_server
    run_server()


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

    agents = data.get("agents", data) if isinstance(data, dict) else data
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


# ============================================================================
# MAIN DISPATCHER
# ============================================================================


COMMANDS = {
    "init":      ("Initialize code-agents in current repo",        cmd_init),
    "start":     ("Start the server",                               cmd_start),
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
    "version":   ("Show version info",                              cmd_version),
}


def cmd_help():
    """Show help."""
    bold, green, yellow, red, cyan, dim = _colors()
    print()
    print(bold(f"  code-agents — AI-powered code agent platform"))
    print()
    print(bold("  Usage:"))
    print(f"    code-agents {cyan('<command>')} [options]")
    print()
    print(bold("  Getting Started:"))
    print(f"    {cyan('init'):<14} Initialize code-agents in current repo")
    print(f"    {cyan('start'):<14} Start the server")
    print(f"    {cyan('setup'):<14} Full interactive setup wizard")
    print()
    print(bold("  Server:"))
    print(f"    {cyan('start'):<14} Start the server")
    print(f"    {cyan('shutdown'):<14} Shutdown the server")
    print(f"    {cyan('status'):<14} Check server health and config")
    print(f"    {cyan('logs'):<14} Tail the log file                    {dim('[lines]')}")
    print(f"    {cyan('config'):<14} Show current .env configuration")
    print(f"    {cyan('doctor'):<14} Diagnose common issues")
    print()
    print(bold("  Git:"))
    print(f"    {cyan('branches'):<14} List git branches")
    print(f"    {cyan('diff'):<14} Show diff between branches           {dim('[base] [head]')}")
    print()
    print(bold("  CI/CD:"))
    print(f"    {cyan('test'):<14} Run tests on the target repo         {dim('[branch]')}")
    print(f"    {cyan('review'):<14} Review code changes with AI          {dim('[base] [head]')}")
    print(f"    {cyan('pipeline'):<14} Manage CI/CD pipeline               {dim('start|status|advance|rollback')}")
    print()
    print(bold("  Other:"))
    print(f"    {cyan('agents'):<14} List all available agents")
    print(f"    {cyan('version'):<14} Show version info")
    print(f"    {cyan('help'):<14} Show this help")
    print()
    print(bold("  Examples:"))
    print(f"    {dim('cd /path/to/your-project')}")
    print(f"    code-agents init                        {dim('# first time setup')}")
    print(f"    code-agents start                       {dim('# run the server')}")
    print(f"    code-agents diff main feature-branch    {dim('# see changes')}")
    print(f"    code-agents test                        {dim('# run tests')}")
    print(f"    code-agents review main HEAD             {dim('# AI code review')}")
    print(f"    code-agents pipeline start               {dim('# start CI/CD')}")
    print()


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
