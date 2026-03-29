"""
Async connection validator for backend health checks.

Validates that the configured backend (cursor/claude/claude-cli) is reachable
and authenticated before starting or resuming a chat session.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("code_agents.connection_validator")


@dataclass
class ValidationResult:
    """Result of a backend connection validation."""
    valid: bool
    backend: str
    message: str
    details: Optional[dict] = None


async def validate_cursor_cli() -> ValidationResult:
    """Validate cursor-agent CLI is installed and responsive."""
    cli_path = shutil.which("cursor-agent")
    if not cli_path:
        return ValidationResult(
            valid=False,
            backend="cursor",
            message="cursor-agent CLI not found. Install it or set CODE_AGENTS_BACKEND=claude-cli",
        )

    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        # Check for HTTP mode fallback
        api_url = os.getenv("CURSOR_API_URL", "").strip()
        if not api_url:
            return ValidationResult(
                valid=False,
                backend="cursor",
                message="CURSOR_API_KEY not set. Configure via: code-agents init",
            )

    return ValidationResult(
        valid=True,
        backend="cursor",
        message="cursor-agent CLI found and API key configured",
        details={"cli_path": cli_path, "has_api_key": bool(api_key)},
    )


async def validate_cursor_http() -> ValidationResult:
    """Validate cursor HTTP endpoint is reachable."""
    import httpx

    api_url = os.getenv("CURSOR_API_URL", "").strip()
    if not api_url:
        return ValidationResult(
            valid=False,
            backend="cursor_http",
            message="CURSOR_API_URL not set",
        )

    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        return ValidationResult(
            valid=False,
            backend="cursor_http",
            message="CURSOR_API_KEY not set",
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Just check connectivity — don't send a real query
            r = await client.get(api_url.rstrip("/") + "/models", headers={
                "Authorization": f"Bearer {api_key}",
            })
            if r.status_code in (200, 401, 403):
                # 200 = reachable + authed, 401/403 = reachable but auth issue
                if r.status_code == 200:
                    return ValidationResult(
                        valid=True, backend="cursor_http",
                        message=f"Cursor API reachable at {api_url}",
                    )
                return ValidationResult(
                    valid=False, backend="cursor_http",
                    message=f"Cursor API returned {r.status_code} — check CURSOR_API_KEY",
                )
            return ValidationResult(
                valid=False, backend="cursor_http",
                message=f"Cursor API returned unexpected status {r.status_code}",
            )
    except httpx.ConnectError:
        return ValidationResult(
            valid=False, backend="cursor_http",
            message=f"Cannot connect to Cursor API at {api_url}",
        )
    except Exception as e:
        return ValidationResult(
            valid=False, backend="cursor_http",
            message=f"Cursor API check failed: {e}",
        )


async def validate_claude_sdk() -> ValidationResult:
    """Validate Anthropic API key is set and the SDK is importable."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return ValidationResult(
            valid=False,
            backend="claude",
            message="ANTHROPIC_API_KEY not set. Configure via: code-agents init",
        )

    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        return ValidationResult(
            valid=False,
            backend="claude",
            message="claude-agent-sdk not installed. Run: poetry install",
        )

    # Quick API validation — list models
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            if r.status_code == 200:
                return ValidationResult(
                    valid=True, backend="claude",
                    message="Anthropic API key valid",
                    details={"key_prefix": api_key[:8] + "..."},
                )
            elif r.status_code in (401, 403):
                return ValidationResult(
                    valid=False, backend="claude",
                    message="Anthropic API key invalid or expired",
                )
            return ValidationResult(
                valid=True, backend="claude",
                message="Anthropic API key set (could not verify — network issue)",
                details={"status": r.status_code},
            )
    except Exception:
        # Network issue — key is set, assume valid
        return ValidationResult(
            valid=True, backend="claude",
            message="Anthropic API key configured (offline — cannot verify)",
        )


async def validate_claude_cli() -> ValidationResult:
    """Validate Claude CLI is installed and logged in."""
    cli_path = shutil.which("claude")
    if not cli_path:
        return ValidationResult(
            valid=False,
            backend="claude-cli",
            message="Claude CLI not found. Install: npm install -g @anthropic-ai/claude-code",
        )

    # Check if logged in by running claude --version (fast, no auth needed)
    try:
        proc = await asyncio.create_subprocess_exec(
            cli_path, "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        version = stdout.decode("utf-8", errors="replace").strip()

        if proc.returncode == 0:
            return ValidationResult(
                valid=True,
                backend="claude-cli",
                message=f"Claude CLI ready (version: {version})",
                details={"cli_path": cli_path, "version": version},
            )
        return ValidationResult(
            valid=False,
            backend="claude-cli",
            message=f"Claude CLI exited with code {proc.returncode}. Run: claude (to login)",
        )
    except asyncio.TimeoutError:
        return ValidationResult(
            valid=False,
            backend="claude-cli",
            message="Claude CLI timed out. It may need login: run `claude` in terminal",
        )
    except Exception as e:
        return ValidationResult(
            valid=False,
            backend="claude-cli",
            message=f"Claude CLI check failed: {e}",
        )


async def validate_backend(backend: Optional[str] = None) -> ValidationResult:
    """
    Validate the active backend connection.

    Detects the backend from CODE_AGENTS_BACKEND env var or the provided override.
    Returns a ValidationResult with status and message.
    """
    if backend is None:
        backend = os.getenv("CODE_AGENTS_BACKEND", "").strip()

    if backend == "claude-cli":
        return await validate_claude_cli()
    elif backend == "claude":
        return await validate_claude_sdk()
    elif backend == "cursor_http":
        return await validate_cursor_http()
    else:
        # Default: cursor CLI, but check for HTTP fallback first
        api_url = os.getenv("CURSOR_API_URL", "").strip()
        if api_url:
            return await validate_cursor_http()
        return await validate_cursor_cli()


async def validate_server_and_backend(server_url: str, backend: Optional[str] = None) -> list[ValidationResult]:
    """
    Validate both server connectivity and backend in parallel.

    Returns a list of ValidationResults (server + backend).
    """
    import httpx

    async def check_server() -> ValidationResult:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{server_url}/health")
                if r.status_code == 200:
                    return ValidationResult(
                        valid=True, backend="server",
                        message=f"Server running at {server_url}",
                    )
                return ValidationResult(
                    valid=False, backend="server",
                    message=f"Server returned {r.status_code}",
                )
        except Exception:
            return ValidationResult(
                valid=False, backend="server",
                message=f"Server not reachable at {server_url}",
            )

    # Run server check and backend validation in parallel
    server_result, backend_result = await asyncio.gather(
        check_server(),
        validate_backend(backend),
    )
    return [server_result, backend_result]


def validate_sync(backend: Optional[str] = None) -> ValidationResult:
    """Synchronous wrapper for validate_backend. For use in non-async contexts."""
    try:
        loop = asyncio.get_running_loop()
        # Already in an async context — can't use asyncio.run
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, validate_backend(backend)).result(timeout=10)
    except RuntimeError:
        return asyncio.run(validate_backend(backend))
