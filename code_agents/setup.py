"""
Interactive one-command setup wizard for Code Agents.

Usage:
    poetry run code-agents-setup

Walks through Python checks, dependency installation, key prompts,
.env generation, and optionally starts the server.
"""

from __future__ import annotations

import datetime
import getpass
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# ANSI color helpers (no dependencies)
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty()


def _wrap(code: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(t: str) -> str:
    return _wrap("1", t)


def green(t: str) -> str:
    return _wrap("32", t)


def yellow(t: str) -> str:
    return _wrap("33", t)


def red(t: str) -> str:
    return _wrap("31", t)


def cyan(t: str) -> str:
    return _wrap("36", t)


def dim(t: str) -> str:
    return _wrap("2", t)


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def prompt(
    label: str,
    default: Optional[str] = None,
    secret: bool = False,
    required: bool = False,
    validator: Optional[Callable[[str], bool]] = None,
    error_msg: str = "Invalid input.",
) -> str:
    """Prompt user for input. Loops on validation failure."""
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            if secret:
                value = getpass.getpass(f"  {label}{suffix}: ")
            else:
                value = input(f"  {label}{suffix}: ")
        except EOFError:
            value = ""

        value = value.strip()
        if not value and default is not None:
            value = default
        if required and not value:
            print(red("    Required — please enter a value."))
            continue
        if value and validator and not validator(value):
            print(red(f"    {error_msg}"))
            continue
        return value


def prompt_yes_no(label: str, default: bool = True) -> bool:
    """Y/n or y/N prompt."""
    hint = "Y/n" if default else "y/N"
    while True:
        try:
            value = input(f"  {label} [{hint}]: ").strip().lower()
        except EOFError:
            value = ""
        if not value:
            return default
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        print(red("    Please enter y or n."))


def prompt_choice(label: str, choices: list[str], default: int = 1) -> int:
    """Numbered choice prompt. Returns 1-based index."""
    for i, c in enumerate(choices, 1):
        marker = bold("*") if i == default else " "
        print(f"    {marker} [{i}] {c}")
    while True:
        try:
            value = input(f"  {label} (default: {default}): ").strip()
        except EOFError:
            value = ""
        if not value:
            return default
        try:
            n = int(value)
            if 1 <= n <= len(choices):
                return n
        except ValueError:
            pass
        print(red(f"    Enter a number 1-{len(choices)}."))


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def validate_url(v: str) -> bool:
    parsed = urllib.parse.urlparse(v)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_port(v: str) -> bool:
    try:
        return 1 <= int(v) <= 65535
    except ValueError:
        return False


def validate_job_path(v: str) -> bool:
    """Jenkins job should be a clean folder path, not a full URL or job/ prefixed path."""
    if v.startswith("http://") or v.startswith("https://"):
        return False
    # Auto-clean: strip job/ prefix if user pasted from Jenkins URL
    cleaned = "/".join(p for p in v.strip("/").split("/") if p and p != "job")
    if cleaned != v.strip("/"):
        print(dim(f"    Auto-cleaned: {v} → {cleaned}"))
    return bool(cleaned)


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------


def print_banner():
    print()
    print(bold(cyan("  ╔══════════════════════════════════════════╗")))
    print(bold(cyan("  ║       Code Agents — Interactive Setup    ║")))
    print(bold(cyan("  ╚══════════════════════════════════════════╝")))
    print()


def check_python() -> None:
    """Step 1: Verify Python >= 3.10."""
    print(bold("[1/7] Checking Python version..."))
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 10):
        print(green(f"  ✓ Python {version_str}"))
    else:
        print(red(f"  ✗ Python {version_str} — requires 3.10+"))
        print(red("    Install Python 3.10+ and try again."))
        sys.exit(1)
    print()


def check_dependencies() -> None:
    """Step 2: Check/install required packages."""
    print(bold("[2/7] Checking dependencies..."))
    missing = []
    for pkg in ["fastapi", "uvicorn", "pydantic", "yaml", "httpx"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if not missing:
        print(green("  ✓ All required packages installed"))
    else:
        print(yellow(f"  ! Missing packages: {', '.join(missing)}"))
        has_poetry = shutil.which("poetry") and Path("pyproject.toml").exists()
        if has_poetry:
            if prompt_yes_no("Install with poetry?", default=True):
                print(dim("    Running: poetry install ..."))
                result = subprocess.run(
                    ["poetry", "install"], capture_output=True, text=True
                )
                if result.returncode == 0:
                    print(green("  ✓ Dependencies installed"))
                else:
                    print(red(f"  ✗ Poetry install failed:\n{result.stderr[:500]}"))
                    sys.exit(1)
            else:
                print(yellow("  Skipping — some features may not work."))
        else:
            req_file = Path("requirements.txt")
            if req_file.exists():
                if prompt_yes_no("Install with pip?", default=True):
                    print(dim(f"    Running: pip install -r requirements.txt ..."))
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                        capture_output=True, text=True,
                    )
                    if result.returncode == 0:
                        print(green("  ✓ Dependencies installed"))
                    else:
                        print(red(f"  ✗ pip install failed:\n{result.stderr[:500]}"))
                        sys.exit(1)
            else:
                print(red("  ✗ Neither poetry nor requirements.txt found."))
                print(red("    Install manually: pip install fastapi uvicorn pydantic pyyaml httpx"))
                sys.exit(1)
    print()


def detect_target_repo() -> dict[str, str]:
    """Step 3: Detect or prompt for the target repository path."""
    print(bold("[3/7] Target Repository"))
    cwd = os.getcwd()
    git_dir = os.path.join(cwd, ".git")

    if os.path.isdir(git_dir):
        print(f"  Detected git repo at: {cyan(cwd)}")
        if prompt_yes_no("Use this as TARGET_REPO_PATH?", default=True):
            print(green(f"  ✓ TARGET_REPO_PATH={cwd}"))
            print()
            return {"TARGET_REPO_PATH": cwd}

    # Manual entry
    path = prompt(
        "Path to target repository",
        default=cwd,
        required=True,
        validator=lambda v: os.path.isdir(v),
        error_msg="Directory does not exist.",
    )
    print(green(f"  ✓ TARGET_REPO_PATH={path}"))
    print()
    return {"TARGET_REPO_PATH": path}


def prompt_backend_keys() -> dict[str, str]:
    """Step 4: Backend API keys."""
    print(bold("[4/7] Backend Configuration"))
    choice = prompt_choice(
        "Which backend?",
        ["Cursor (default)", "Claude", "Both"],
        default=1,
    )

    env = {}

    if choice in (1, 3):  # Cursor
        env["CURSOR_API_KEY"] = prompt(
            "CURSOR_API_KEY",
            secret=True,
            required=True,
        )
        url = prompt(
            "Cursor API URL (blank for CLI mode)",
            validator=lambda v: validate_url(v),
            error_msg="Must be a valid URL (https://...)",
        )
        if url:
            env["CURSOR_API_URL"] = url

    if choice in (2, 3):  # Claude
        env["ANTHROPIC_API_KEY"] = prompt(
            "ANTHROPIC_API_KEY",
            secret=True,
            required=True,
        )

    print()
    return env


def prompt_server_config() -> dict[str, str]:
    """Step 5: Server host and port."""
    print(bold("[5/7] Server Configuration"))
    host = prompt("HOST", default="0.0.0.0")
    port = prompt(
        "PORT",
        default="8000",
        validator=validate_port,
        error_msg="Must be a number 1-65535.",
    )
    print()
    return {"HOST": host, "PORT": port}


def prompt_cicd_pipeline() -> dict[str, str]:
    """Step 6: CI/CD pipeline — Jenkins, ArgoCD, Testing."""
    print(bold("[6/7] CI/CD Pipeline (optional)"))
    env: dict[str, str] = {}

    # Jenkins
    if prompt_yes_no("Configure Jenkins?", default=False):
        print(dim("    Jenkins base URL without job path"))
        print(dim("    Example: https://jenkins.pg2nonprod.paytmpayments.in/"))
        env["JENKINS_URL"] = prompt(
            "JENKINS_URL",
            default="https://jenkins.pg2nonprod.paytmpayments.in/",
            required=True,
            validator=validate_url,
            error_msg="Must be a valid URL.",
        )
        print(dim("    Jenkins user with API token access"))
        print(dim("    Example: shivanshu1.gupta@paytmpayments.com"))
        env["JENKINS_USERNAME"] = prompt("JENKINS_USERNAME", required=True)
        print(dim("    Manage Jenkins → Users → Configure → API Token"))
        env["JENKINS_API_TOKEN"] = prompt("JENKINS_API_TOKEN", secret=True, required=True)
        print()
        print(dim("    Use the folder path from your Jenkins URL, separated by /"))
        print(dim("    Example: If your Jenkins URL is:"))
        print(dim("      https://jenkins.company.com/job/pg2/job/pg2-dev-build-jobs/job/pg2-dev-pg-acquiring-biz/"))
        print(dim("    Then the job path is: pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz"))
        print(dim("    DO NOT include 'job/' prefix — just use folder names separated by /"))
        print()
        env["JENKINS_BUILD_JOB"] = prompt(
            "JENKINS_BUILD_JOB",
            default="pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz",
            required=True,
            validator=validate_job_path,
            error_msg="Enter a job path like 'pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz', not a full URL.",
        )
        print(dim("    Deploy job path (same as build job if same pipeline)"))
        print(dim("    Example: pg2/pg2-dev-build-jobs/deploy"))
        env["JENKINS_DEPLOY_JOB"] = prompt(
            "JENKINS_DEPLOY_JOB",
            default=env.get("JENKINS_BUILD_JOB", ""),
            validator=validate_job_path,
            error_msg="Enter a job path, not a full URL.",
        )

    # ArgoCD
    if prompt_yes_no("Configure ArgoCD?", default=False):
        print(dim("    ArgoCD server URL"))
        print(dim("    Example: https://argocd-acquiring.pg2prod.paytm.com"))
        env["ARGOCD_URL"] = prompt(
            "ARGOCD_URL",
            required=True,
            validator=validate_url,
            error_msg="Must be a valid URL.",
        )
        print(dim("    Generate via: argocd account generate-token --account <user>"))
        env["ARGOCD_AUTH_TOKEN"] = prompt("ARGOCD_AUTH_TOKEN", secret=True, required=True)
        print(dim("    Must match the app name in ArgoCD UI exactly"))
        print(dim("    Example: pg-acquiring-biz"))
        env["ARGOCD_APP_NAME"] = prompt("ARGOCD_APP_NAME", required=True)

    # Testing overrides
    if prompt_yes_no("Configure testing overrides?", default=False):
        print(dim("    Hint: Shell command to run tests. Leave blank to auto-detect (pytest/jest/maven/go)"))
        print(dim("    Example: pytest --cov --cov-report=xml:coverage.xml"))
        cmd = prompt("TARGET_TEST_COMMAND (blank for auto-detect)")
        if cmd:
            env["TARGET_TEST_COMMAND"] = cmd
        print(dim("    Hint: Minimum coverage % required (default: 100)"))
        threshold = prompt("TARGET_COVERAGE_THRESHOLD", default="100")
        if threshold != "100":
            env["TARGET_COVERAGE_THRESHOLD"] = threshold

    print()
    return env


def prompt_integrations() -> dict[str, str]:
    """Step 7: Optional integrations — Elasticsearch, Atlassian, Redash."""
    print(bold("[7/7] Other Integrations (optional)"))
    env: dict[str, str] = {}

    # Elasticsearch
    if prompt_yes_no("Configure Elasticsearch?", default=False):
        env["ELASTICSEARCH_URL"] = prompt(
            "ELASTICSEARCH_URL",
            validator=validate_url,
            error_msg="Must be a valid URL.",
        )
        api_key = prompt("ELASTICSEARCH_API_KEY (blank to skip)")
        if api_key:
            env["ELASTICSEARCH_API_KEY"] = api_key

    # Atlassian OAuth
    if prompt_yes_no("Configure Atlassian OAuth?", default=False):
        env["ATLASSIAN_OAUTH_CLIENT_ID"] = prompt("ATLASSIAN_OAUTH_CLIENT_ID", required=True)
        env["ATLASSIAN_OAUTH_CLIENT_SECRET"] = prompt(
            "ATLASSIAN_OAUTH_CLIENT_SECRET", secret=True, required=True,
        )
        env["ATLASSIAN_CLOUD_SITE_URL"] = prompt(
            "ATLASSIAN_CLOUD_SITE_URL (e.g. https://company.atlassian.net)",
            validator=validate_url,
            error_msg="Must be a valid URL.",
        )

    # Redash
    if prompt_yes_no("Configure Redash?", default=False):
        env["REDASH_BASE_URL"] = prompt(
            "REDASH_BASE_URL",
            required=True,
            validator=validate_url,
            error_msg="Must be a valid URL.",
        )
        api_key = prompt("REDASH_API_KEY (blank for username/password auth)")
        if api_key:
            env["REDASH_API_KEY"] = api_key
        else:
            env["REDASH_USERNAME"] = prompt("REDASH_USERNAME", required=True)
            env["REDASH_PASSWORD"] = prompt("REDASH_PASSWORD", secret=True, required=True)

    print()
    return env


# ---------------------------------------------------------------------------
# .env file writer
# ---------------------------------------------------------------------------

_ENV_SECTIONS = [
    ("# Core", ["CURSOR_API_KEY", "CURSOR_API_URL", "CODE_AGENTS_HTTP_ONLY", "ANTHROPIC_API_KEY"]),
    ("# Server", ["HOST", "PORT", "LOG_LEVEL", "CODE_AGENTS_PUBLIC_BASE_URL", "OPEN_WEBUI_PUBLIC_URL"]),
    ("# Target Repository", ["TARGET_REPO_PATH", "TARGET_REPO_REMOTE"]),
    ("# Testing", ["TARGET_TEST_COMMAND", "TARGET_COVERAGE_THRESHOLD"]),
    ("# Jenkins", ["JENKINS_URL", "JENKINS_USERNAME", "JENKINS_API_TOKEN", "JENKINS_BUILD_JOB", "JENKINS_DEPLOY_JOB"]),
    ("# ArgoCD", ["ARGOCD_URL", "ARGOCD_AUTH_TOKEN", "ARGOCD_APP_NAME", "ARGOCD_VERIFY_SSL"]),
    ("# Elasticsearch", ["ELASTICSEARCH_URL", "ELASTICSEARCH_CLOUD_ID", "ELASTICSEARCH_API_KEY",
                          "ELASTICSEARCH_USERNAME", "ELASTICSEARCH_PASSWORD", "ELASTICSEARCH_CA_CERTS",
                          "ELASTICSEARCH_VERIFY_SSL"]),
    ("# Atlassian OAuth", ["ATLASSIAN_OAUTH_CLIENT_ID", "ATLASSIAN_OAUTH_CLIENT_SECRET",
                           "ATLASSIAN_OAUTH_SCOPES", "ATLASSIAN_CLOUD_SITE_URL",
                           "ATLASSIAN_OAUTH_SUCCESS_REDIRECT", "CODE_AGENTS_HTTPS_VERIFY"]),
    ("# Redash", ["REDASH_BASE_URL", "REDASH_API_KEY", "REDASH_USERNAME", "REDASH_PASSWORD"]),
]


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict."""
    result = {}
    if not path.exists() or not path.is_file():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)', line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()
            # Remove surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            result[key] = value
    return result


def _write_env_to_path(env_path: Path, env_vars: dict[str, str], label: str) -> None:
    """Write env vars to a specific path with section grouping."""
    # Ensure parent directory exists
    env_path.parent.mkdir(parents=True, exist_ok=True)

    if env_path.exists():
        existing = parse_env_file(env_path)
        existing_count = len(existing)
        print(f"  Found existing {label} with {existing_count} configured variables.")
        print(f"    [O] Overwrite with new values")
        print(f"    [M] Merge (keep existing, add new)")
        print(f"    [B] Backup existing, then overwrite")
        print(f"    [C] Cancel")
        while True:
            try:
                choice = input("  Choice [M]: ").strip().lower() or "m"
            except EOFError:
                choice = "c"
            if choice in ("o", "m", "b", "c"):
                break
            print(red("    Enter O, M, B, or C."))

        if choice == "c":
            print(yellow(f"  Skipped — {label} not modified."))
            return
        if choice == "b":
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = env_path.with_suffix(f".backup.{ts}")
            shutil.copy2(env_path, backup)
            print(green(f"  ✓ Backed up to {backup}"))
        if choice == "m":
            merged = dict(existing)
            added = 0
            for k, v in env_vars.items():
                if k not in merged:
                    merged[k] = v
                    added += 1
            env_vars = merged
            print(dim(f"    Merged: {added} new keys added, {existing_count} existing kept."))

    # Build the file content with sections
    lines = [f"# Generated by code-agents init — {label}", ""]
    written_keys: set[str] = set()

    for section_comment, keys in _ENV_SECTIONS:
        section_vars = {k: env_vars[k] for k in keys if k in env_vars}
        if section_vars:
            lines.append(section_comment)
            for k, v in section_vars.items():
                if " " in v:
                    lines.append(f'{k}="{v}"')
                else:
                    lines.append(f"{k}={v}")
                written_keys.add(k)
            lines.append("")

    remaining = {k: v for k, v in env_vars.items() if k not in written_keys}
    if remaining:
        lines.append("# Other")
        for k, v in remaining.items():
            if " " in v:
                lines.append(f'{k}="{v}"')
            else:
                lines.append(f"{k}={v}")
        lines.append("")

    content = "\n".join(lines)
    env_path.write_text(content)

    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass

    count = len(env_vars)
    print(green(f"  ✓ {label} written ({count} variables, permissions: 600)"))
    print(f"    {dim(str(env_path))}")
    print()


def write_env_file(env_vars: dict[str, str]) -> None:
    """Write env vars to centralized global + per-repo config files."""
    from .env_loader import GLOBAL_ENV_PATH, PER_REPO_FILENAME, split_vars

    global_vars, repo_vars = split_vars(env_vars)

    if global_vars:
        print(bold("  Writing global config (API keys, server, integrations):"))
        _write_env_to_path(GLOBAL_ENV_PATH, global_vars, "global config")

    if repo_vars:
        print(bold("  Writing per-repo config (Jenkins, ArgoCD, testing):"))
        _write_env_to_path(Path(PER_REPO_FILENAME), repo_vars, "repo config")


# ---------------------------------------------------------------------------
# Server launcher
# ---------------------------------------------------------------------------


def start_server() -> None:
    """Load .env and start the Code Agents server."""
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(".env"))
    except ImportError:
        pass

    print(bold(cyan("  Starting Code Agents...")))
    host = os.getenv("HOST", "0.0.0.0")
    port = os.getenv("PORT", "8000")
    print(dim(f"  Server: http://{host}:{port}"))
    print(dim("  Press Ctrl+C to stop.\n"))

    from code_agents.main import main as run_server
    run_server()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    try:
        print_banner()
        check_python()
        check_dependencies()

        env_vars: dict[str, str] = {}
        env_vars.update(detect_target_repo())
        env_vars.update(prompt_backend_keys())
        env_vars.update(prompt_server_config())
        env_vars.update(prompt_cicd_pipeline())
        env_vars.update(prompt_integrations())

        # Filter out empty values
        env_vars = {k: v for k, v in env_vars.items() if v}

        print(bold("━" * 44))
        write_env_file(env_vars)

        if prompt_yes_no("Start the server now?", default=True):
            start_server()
        else:
            print()
            print(green("  Setup complete!"))
            print(f"  Run the server with: {cyan('poetry run code-agents')}")
            print()

    except KeyboardInterrupt:
        print(yellow("\n\n  Setup cancelled."))
        sys.exit(0)
    except EOFError:
        print(yellow("\n\n  Setup cancelled (no input)."))
        sys.exit(0)


if __name__ == "__main__":
    main()
