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
# Helpers (extracted to cli_helpers.py)
# ---------------------------------------------------------------------------

from .cli_helpers import (  # noqa: F401
    _find_code_agents_home, _user_cwd, _load_env, _colors,
    _server_url, _api_get, _api_post, prompt_yes_no,
    _check_workspace_trust,
)


# ============================================================================
# COMMANDS
# ============================================================================


_INIT_SECTIONS = {
    "--backend":  "Backend API keys (Cursor/Claude)",
    "--server":   "Server host and port",
    "--jenkins":  "Jenkins CI/CD build and deploy",
    "--argocd":   "ArgoCD deployment verification",
    "--redash":   "Redash database queries",
    "--elastic":  "Elasticsearch integration",
    "--atlassian": "Atlassian OAuth (Jira/Confluence)",
    "--testing":  "Testing overrides (command, coverage threshold)",
}


def cmd_init():
    """Initialize code-agents in the current repository.

    Usage:
      code-agents init               # full wizard (all sections)
      code-agents init --jenkins     # update Jenkins config only
      code-agents init --redash      # update Redash config only
      code-agents init --argocd      # update ArgoCD config only
      code-agents init --backend     # update API keys only
      code-agents init --server      # update host/port only
      code-agents init --elastic     # update Elasticsearch only
      code-agents init --atlassian   # update Atlassian OAuth only
      code-agents init --testing     # update test command/threshold only
    """
    from .setup import (
        prompt, prompt_yes_no, prompt_choice, prompt_cicd_pipeline,
        prompt_integrations, write_env_file, validate_url, validate_port,
    )
    bold, green, yellow, red, cyan, dim = _colors()

    cwd = _user_cwd()
    code_agents_home = _find_code_agents_home()
    args = sys.argv[2:]  # everything after 'init'

    # Determine which sections to run
    section_flags = [a for a in args if a.startswith("--") and a in _INIT_SECTIONS]
    run_all = not section_flags  # no flags = full wizard

    print()
    print(bold(cyan("  ╔══════════════════════════════════════════════╗")))
    print(bold(cyan("  ║       Code Agents — Init Repository          ║")))
    print(bold(cyan("  ╚══════════════════════════════════════════════╝")))
    print()

    if run_all:
        if os.path.isdir(os.path.join(cwd, ".git")):
            print(green(f"  ✓ Git repo detected: {cwd}"))
        else:
            print(yellow(f"  ! No .git found in: {cwd}"))
            if not prompt_yes_no("Continue anyway?", default=False):
                print(yellow("  Cancelled."))
                return
        print(f"  Code Agents installed at: {dim(str(code_agents_home))}")
    else:
        sections_desc = ", ".join(_INIT_SECTIONS[f] for f in section_flags)
        print(f"  Updating: {bold(sections_desc)}")
        print(f"  Repo: {cwd}")
    print()

    # Load existing config to merge with
    from .env_loader import GLOBAL_ENV_PATH, PER_REPO_FILENAME
    from .setup import parse_env_file
    existing_global = parse_env_file(GLOBAL_ENV_PATH) if GLOBAL_ENV_PATH.is_file() else {}
    existing_repo = parse_env_file(Path(os.path.join(cwd, PER_REPO_FILENAME))) if os.path.isfile(os.path.join(cwd, PER_REPO_FILENAME)) else {}
    existing = {**existing_global, **existing_repo}

    env_vars: dict[str, str] = {}

    # Backend
    if run_all or "--backend" in section_flags:
        print(bold("  Backend Configuration"))
        choice = prompt_choice(
            "Which backend?",
            [
                "Cursor (default — needs CURSOR_API_KEY)",
                "Claude API (needs ANTHROPIC_API_KEY)",
                "Claude CLI (uses your Claude subscription — no API key)",
                "Both Cursor + Claude API",
            ],
            default=1,
        )
        if choice in (1, 4):
            env_vars["CURSOR_API_KEY"] = prompt("CURSOR_API_KEY", default=existing.get("CURSOR_API_KEY", ""), secret=True, required=True)
            url = prompt("Cursor API URL (blank for CLI mode)", default=existing.get("CURSOR_API_URL", ""), validator=validate_url, error_msg="Must be a valid URL")
            if url:
                env_vars["CURSOR_API_URL"] = url
        if choice in (2, 4):
            env_vars["ANTHROPIC_API_KEY"] = prompt("ANTHROPIC_API_KEY", default=existing.get("ANTHROPIC_API_KEY", ""), secret=True, required=True)
        if choice == 3:
            env_vars["CODE_AGENTS_BACKEND"] = "claude-cli"
            print(dim("    Claude CLI uses your Claude Pro/Max subscription."))
            print(dim("    Make sure you're logged in: run 'claude' in terminal first."))
            model = prompt("Claude model", default="claude-sonnet-4-6")
            env_vars["CODE_AGENTS_CLAUDE_CLI_MODEL"] = model
        print()

    # Server
    if run_all or "--server" in section_flags:
        print(bold("  Server Configuration"))
        env_vars["HOST"] = prompt("HOST", default=existing.get("HOST", "0.0.0.0"))
        env_vars["PORT"] = prompt("PORT", default=existing.get("PORT", "8000"), validator=validate_port, error_msg="Must be 1-65535")
        print()

    # Jenkins
    if run_all or "--jenkins" in section_flags:
        should_configure = True if "--jenkins" in section_flags else prompt_yes_no("Configure Jenkins?", default=False)
        if should_configure:
            from .setup import validate_job_path, clean_job_path
            print(dim("    Jenkins base URL without job path"))
            print(dim("    Example: https://jenkins.pg2nonprod.paytmpayments.in/"))
            env_vars["JENKINS_URL"] = prompt(
                "JENKINS_URL",
                default=existing.get("JENKINS_URL", "https://jenkins.pg2nonprod.paytmpayments.in/"),
                required=True, validator=validate_url, error_msg="Must be a valid URL.",
            )
            print(dim("    Example: shivanshu1.gupta@paytmpayments.com"))
            env_vars["JENKINS_USERNAME"] = prompt("JENKINS_USERNAME", default=existing.get("JENKINS_USERNAME", ""), required=True)
            print(dim("    Manage Jenkins → Users → Configure → API Token"))
            env_vars["JENKINS_API_TOKEN"] = prompt("JENKINS_API_TOKEN", default=existing.get("JENKINS_API_TOKEN", ""), secret=True, required=True)
            print()
            print(dim("    Extract folder path from Jenkins URL (no 'job/' prefix)"))
            print(dim("    Example: pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz"))
            env_vars["JENKINS_BUILD_JOB"] = prompt(
                "JENKINS_BUILD_JOB",
                default=existing.get("JENKINS_BUILD_JOB", "pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz"),
                required=True, validator=validate_job_path,
                transform=clean_job_path,
                error_msg="Enter folder path, not full URL.",
            )
            print(dim("    Deploy job (same as build job if same pipeline)"))
            env_vars["JENKINS_DEPLOY_JOB"] = prompt(
                "JENKINS_DEPLOY_JOB",
                default=existing.get("JENKINS_DEPLOY_JOB", env_vars.get("JENKINS_BUILD_JOB", "")),
                validator=validate_job_path, transform=clean_job_path,
                error_msg="Enter folder path.",
            )
            print()

    # ArgoCD
    if run_all or "--argocd" in section_flags:
        should_configure = True if "--argocd" in section_flags else prompt_yes_no("Configure ArgoCD?", default=False)
        if should_configure:
            print(dim("    Example: https://argocd-acquiring.pg2prod.paytm.com"))
            env_vars["ARGOCD_URL"] = prompt("ARGOCD_URL", default=existing.get("ARGOCD_URL", ""), required=True, validator=validate_url, error_msg="Must be a valid URL.")
            print(dim("    argocd account generate-token --account <user>"))
            env_vars["ARGOCD_AUTH_TOKEN"] = prompt("ARGOCD_AUTH_TOKEN", default=existing.get("ARGOCD_AUTH_TOKEN", ""), secret=True, required=True)
            print(dim("    Example: pg-acquiring-biz"))
            env_vars["ARGOCD_APP_NAME"] = prompt("ARGOCD_APP_NAME", default=existing.get("ARGOCD_APP_NAME", ""), required=True)
            print()

    # Testing
    if run_all or "--testing" in section_flags:
        should_configure = True if "--testing" in section_flags else prompt_yes_no("Configure testing overrides?", default=False)
        if should_configure:
            print(dim("    Leave blank for auto-detect (pytest/jest/maven/go)"))
            print(dim("    Example: pytest --cov --cov-report=xml:coverage.xml"))
            cmd = prompt("TARGET_TEST_COMMAND", default=existing.get("TARGET_TEST_COMMAND", ""))
            if cmd:
                env_vars["TARGET_TEST_COMMAND"] = cmd
            threshold = prompt("TARGET_COVERAGE_THRESHOLD", default=existing.get("TARGET_COVERAGE_THRESHOLD", "100"))
            if threshold != "100":
                env_vars["TARGET_COVERAGE_THRESHOLD"] = threshold
            print()

    # Integrations (only in full wizard or specific flags)
    if run_all:
        env_vars.update(prompt_integrations())
    else:
        if "--redash" in section_flags:
            from .setup import validate_url as _vurl
            print(bold("  Redash Configuration"))
            print(dim("    Example: http://10.215.50.126/"))
            env_vars["REDASH_BASE_URL"] = prompt("REDASH_BASE_URL", default=existing.get("REDASH_BASE_URL", ""), required=True, validator=_vurl, error_msg="Must be a valid URL.")
            api_key = prompt("REDASH_API_KEY (blank for username/password)", default=existing.get("REDASH_API_KEY", ""))
            if api_key:
                env_vars["REDASH_API_KEY"] = api_key
            else:
                env_vars["REDASH_USERNAME"] = prompt("REDASH_USERNAME", default=existing.get("REDASH_USERNAME", ""), required=True)
                env_vars["REDASH_PASSWORD"] = prompt("REDASH_PASSWORD", default=existing.get("REDASH_PASSWORD", ""), secret=True, required=True)
            print()

        if "--elastic" in section_flags:
            print(bold("  Elasticsearch Configuration"))
            env_vars["ELASTICSEARCH_URL"] = prompt("ELASTICSEARCH_URL", default=existing.get("ELASTICSEARCH_URL", ""), required=True)
            api_key = prompt("ELASTICSEARCH_API_KEY (blank to skip)", default=existing.get("ELASTICSEARCH_API_KEY", ""))
            if api_key:
                env_vars["ELASTICSEARCH_API_KEY"] = api_key
            print()

        if "--atlassian" in section_flags:
            print(bold("  Atlassian OAuth Configuration"))
            env_vars["ATLASSIAN_CLOUD_SITE_URL"] = prompt("ATLASSIAN_CLOUD_SITE_URL", default=existing.get("ATLASSIAN_CLOUD_SITE_URL", ""), required=True)
            env_vars["ATLASSIAN_OAUTH_CLIENT_ID"] = prompt("ATLASSIAN_OAUTH_CLIENT_ID", default=existing.get("ATLASSIAN_OAUTH_CLIENT_ID", ""), required=True)
            env_vars["ATLASSIAN_OAUTH_CLIENT_SECRET"] = prompt("ATLASSIAN_OAUTH_CLIENT_SECRET", default=existing.get("ATLASSIAN_OAUTH_CLIENT_SECRET", ""), secret=True, required=True)
            print()

    env_vars = {k: v for k, v in env_vars.items() if v}

    if not env_vars:
        print(dim("  No changes to save."))
        return

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

    # Check if server is already running
    port = os.getenv("PORT", "8000")
    server_running = False
    try:
        import httpx
        r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
        server_running = r.status_code == 200
    except Exception:
        pass

    if server_running:
        print(yellow(f"  Server is already running on port {port}."))
        if prompt_yes_no("Restart the server to apply new config?", default=True):
            cmd_restart()
        else:
            print(dim("  Config saved. Restart manually: code-agents restart"))
            print()
    elif prompt_yes_no("Start the server now?", default=True):
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


# _check_workspace_trust moved to cli_helpers.py (imported above)


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


def cmd_sessions(args: list[str] | None = None):
    """List and manage saved chat sessions."""
    bold, green, yellow, red, cyan, dim = _colors()
    from datetime import datetime
    from .chat_history import list_sessions, delete_session

    args = args or []
    cwd = _user_cwd()

    # Sub-commands: list (default), delete <N>, clear
    sub = args[0] if args else "list"

    if sub == "clear":
        from .chat_history import HISTORY_DIR
        import shutil
        if HISTORY_DIR.exists():
            count = len(list(HISTORY_DIR.glob("*.json")))
            if count == 0:
                print(dim("  No sessions to clear."))
                return
            print(f"  This will delete {bold(str(count))} saved chat sessions.")
            try:
                answer = input("  Are you sure? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if answer in ("y", "yes"):
                shutil.rmtree(HISTORY_DIR)
                HISTORY_DIR.mkdir(parents=True, exist_ok=True)
                print(green(f"  \u2713 Cleared {count} sessions."))
            else:
                print(dim("  Cancelled."))
        else:
            print(dim("  No sessions to clear."))
        return

    if sub == "delete":
        if len(args) < 2:
            print(yellow("  Usage: code-agents sessions delete <session-id>"))
            return
        sid = args[1].strip()
        if delete_session(sid):
            print(green(f"  \u2713 Deleted session: {sid}"))
        else:
            print(red(f"  Session '{sid}' not found."))
            print(dim("  Use 'code-agents sessions' to see session IDs."))
        return

    # Default: list sessions
    show_all = "--all" in args
    repo_path = None if show_all else cwd
    # Find git root
    if not show_all:
        check_dir = cwd
        while True:
            if os.path.isdir(os.path.join(check_dir, ".git")):
                repo_path = check_dir
                break
            parent = os.path.dirname(check_dir)
            if parent == check_dir:
                repo_path = cwd
                break
            check_dir = parent

    sessions = list_sessions(limit=20, repo_path=repo_path)

    print()
    if not sessions:
        print(dim("  No saved chat sessions."))
        if not show_all:
            print(dim("  Use --all to show sessions from all repos."))
        print()
        return

    print(bold("  Saved chat sessions:"))
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
    print(f"  {dim('Resume:  code-agents chat --resume <session-id>')}")
    print(f"  {dim('Delete:  code-agents sessions delete <session-id>')}")
    print(f"  {dim('Clear:   code-agents sessions clear')}")
    if not show_all:
        print(f"  {dim('All:     code-agents sessions --all')}")
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


def cmd_update():
    """Update code-agents to the latest version from git."""
    import subprocess as _sp
    bold, green, yellow, red, cyan, dim = _colors()

    home = _find_code_agents_home()
    print()
    print(bold(cyan("  Updating Code Agents...")))
    print(f"  Install dir: {dim(str(home))}")
    print()

    # Check if it's a git repo
    if not (home / ".git").is_dir():
        print(red("  ✗ Not a git repository — cannot update."))
        print(dim(f"    Re-install: curl -fsSL https://raw.githubusercontent.com/shivanshu1gupta-paytmpayments/code-agents/main/install.sh | bash"))
        return

    # Save current commit
    old_commit = _sp.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(home), capture_output=True, text=True,
    ).stdout.strip()

    # Check current branch
    current_branch = _sp.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(home), capture_output=True, text=True,
    ).stdout.strip() or "main"

    # Check remote URL and fix SSH → HTTPS if SSH fails
    remote_url = _sp.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(home), capture_output=True, text=True,
    ).stdout.strip()
    print(f"  Remote: {dim(remote_url)}")
    print(f"  Branch: {dim(current_branch)}")
    print()

    # Pull latest — try current remote first
    print(dim("  Pulling latest changes..."))
    pull = _sp.run(
        ["git", "pull", "origin", current_branch],
        cwd=str(home), capture_output=True, text=True,
        timeout=30,
    )

    # If SSH fails, try switching to HTTPS
    if pull.returncode != 0 and "git@github.com:" in remote_url:
        https_url = remote_url.replace("git@github.com:", "https://github.com/")
        if not https_url.endswith(".git"):
            https_url += ".git"
        print(yellow("  SSH failed — trying HTTPS..."))
        _sp.run(
            ["git", "remote", "set-url", "origin", https_url],
            cwd=str(home), capture_output=True, text=True,
        )
        pull = _sp.run(
            ["git", "pull", "origin", current_branch],
            cwd=str(home), capture_output=True, text=True,
            timeout=30,
        )
        if pull.returncode != 0:
            # Restore original URL
            _sp.run(
                ["git", "remote", "set-url", "origin", remote_url],
                cwd=str(home), capture_output=True, text=True,
            )

    if pull.returncode != 0:
        print(red(f"  ✗ git pull failed:"))
        for line in (pull.stderr or pull.stdout).splitlines()[:5]:
            print(f"    {line}")
        print()
        print(dim("  Possible fixes:"))
        print(dim("    1. Check internet connection / VPN"))
        print(dim("    2. Switch to HTTPS: git remote set-url origin https://github.com/shivanshu1gupta-paytmpayments/code-agents.git"))
        print(dim("    3. Re-install: curl -fsSL https://raw.githubusercontent.com/shivanshu1gupta-paytmpayments/code-agents/main/install.sh | bash"))
        print()
        return

    new_commit = _sp.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(home), capture_output=True, text=True,
    ).stdout.strip()

    if old_commit == new_commit:
        print(green("  ✓ Already up to date."))
        print()
        return

    # Show what changed
    changed = _sp.run(
        ["git", "diff", "--stat", f"{old_commit}..{new_commit}"],
        cwd=str(home), capture_output=True, text=True,
    ).stdout.strip()
    commits = _sp.run(
        ["git", "log", "--oneline", f"{old_commit}..{new_commit}"],
        cwd=str(home), capture_output=True, text=True,
    ).stdout.strip()

    if commits:
        print(bold("  New commits:"))
        for line in commits.splitlines():
            print(f"    {dim(line)}")
        print()

    if changed:
        # Count files
        lines = changed.splitlines()
        print(f"  {bold(str(len(lines) - 1))} file(s) changed")
        print()

    # Reinstall dependencies
    print(dim("  Installing dependencies..."))
    install = _sp.run(
        ["poetry", "install", "--quiet"],
        cwd=str(home), capture_output=True, text=True,
    )
    if install.returncode != 0:
        print(yellow(f"  ! poetry install had issues:"))
        for line in install.stderr.splitlines()[:5]:
            print(f"    {line}")
    else:
        print(green("  ✓ Dependencies updated."))

    print()
    print(green(bold(f"  ✓ Updated: {old_commit} → {new_commit}")))
    print()
    print(dim("  Restart the server to apply: code-agents restart"))
    print()


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
    "sessions":  ("List saved chat sessions",                       None),  # special handling
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
    "update":    ("Update code-agents to latest version",            cmd_update),
    "version":   ("Show version info",                              cmd_version),
    "completions": ("Generate shell completion script",             None),  # special handling
}


# ---------------------------------------------------------------------------
# Completions and help (extracted to cli_completions.py)
# ---------------------------------------------------------------------------

from .cli_completions import (  # noqa: F401
    _AGENT_NAMES_FOR_COMPLETION, _SUBCOMMANDS,
    _generate_zsh_completion, _generate_bash_completion,
    cmd_completions, cmd_help,
)


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
        elif command == "update":
            cmd_update()
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
        elif command == "sessions":
            cmd_sessions(rest)
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
