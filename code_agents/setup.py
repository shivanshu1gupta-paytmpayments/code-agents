"""
Interactive one-command setup wizard for Code Agents.

Usage:
    poetry run code-agents-setup

Walks through Python checks, dependency installation, key prompts,
.env generation, and optionally starts the server.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Re-export from split modules for backward compatibility
from .setup_ui import (  # noqa: F401
    bold, green, yellow, red, cyan, dim,
    prompt, prompt_yes_no, prompt_choice,
    validate_url, validate_port, validate_job_path, clean_job_path,
)
from .setup_env import (  # noqa: F401
    _ENV_SECTIONS, parse_env_file, _write_env_to_path, write_env_file,
)

# ---------------------------------------------------------------------------
# ANSI color helpers (no dependencies)
# ---------------------------------------------------------------------------


# UI helpers moved to setup_ui.py, env management moved to setup_env.py

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
        print(dim("    Example: https://jenkins.mycompany.com/"))
        env["JENKINS_URL"] = prompt(
            "JENKINS_URL",
            required=True,
            validator=validate_url,
            error_msg="Must be a valid URL.",
        )
        print(dim("    Jenkins user with API token access"))
        env["JENKINS_USERNAME"] = prompt("JENKINS_USERNAME", required=True)
        print(dim("    Manage Jenkins → Users → Configure → API Token"))
        env["JENKINS_API_TOKEN"] = prompt("JENKINS_API_TOKEN", secret=True, required=True)
        print()
        print(dim("    Use the folder path from your Jenkins URL, separated by /"))
        print(dim("    Example: If your Jenkins URL is:"))
        print(dim("      https://jenkins.company.com/job/folder/job/subfolder/job/my-service/"))
        print(dim("    Then the job path is: folder/subfolder/my-service"))
        print(dim("    DO NOT include 'job/' prefix — just use folder names separated by /"))
        print()
        env["JENKINS_BUILD_JOB"] = prompt(
            "JENKINS_BUILD_JOB",
            required=True,
            validator=validate_job_path,
            transform=clean_job_path,
            error_msg="Enter a job path like 'folder/subfolder/my-service', not a full URL.",
        )
        print(dim("    Deploy job path (same as build job if same pipeline)"))
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


# _ENV_SECTIONS, parse_env_file, _write_env_to_path, write_env_file → setup_env.py

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
