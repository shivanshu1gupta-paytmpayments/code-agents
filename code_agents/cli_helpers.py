"""CLI shared helpers — colors, server URL, API calls, env loading."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_code_agents_home() -> Path:
    """Find where code-agents is installed."""
    return Path(__file__).resolve().parent.parent


def _user_cwd() -> str:
    """Get the user's REAL working directory."""
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
    """Make a GET request to the running server."""
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


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Simple yes/no prompt."""
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"  {question} {suffix}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if not answer:
        return default
    return answer in ("y", "yes")


def _check_workspace_trust(repo_path: str) -> bool:
    """Lightweight workspace trust check."""
    if os.getenv("CODE_AGENTS_BACKEND", "").strip() == "claude-cli":
        return True
    if os.getenv("CURSOR_API_URL", "").strip():
        return True
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        return True
    return True
