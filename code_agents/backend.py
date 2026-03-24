from __future__ import annotations

import json
import logging
import os
import shutil
from typing import AsyncIterator, Optional

from .config import AgentConfig
from .message_types import AssistantMessage, ResultMessage, SystemMessage, TextBlock

logger = logging.getLogger("code_agents.backend")


async def _run_cursor_http(
    agent: AgentConfig,
    prompt: str,
    model: str,
) -> AsyncIterator:
    """Call an OpenAI-compatible Cursor API URL with API key (no cursor-agent CLI or desktop app)."""
    import httpx

    from .message_types import (
        AssistantMessage,
        ResultMessage,
        SystemMessage,
        TextBlock,
    )

    base_url = (agent.extra_args or {}).get("cursor_api_url") or os.getenv("CURSOR_API_URL")
    if not base_url or not str(base_url).strip():
        raise RuntimeError(
            "cursor_http backend requires cursor_api_url. "
            "Set extra_args.cursor_api_url in agent YAML or CURSOR_API_URL in environment."
        )
    base_url = str(base_url).rstrip("/")
    api_key = agent.api_key or os.getenv("CURSOR_API_KEY")
    if not api_key:
        raise RuntimeError("cursor_http backend requires CURSOR_API_KEY in agent config or environment.")

    messages = []
    if agent.system_prompt and agent.system_prompt.strip():
        messages.append({"role": "system", "content": agent.system_prompt.strip()})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {"model": model, "messages": messages, "stream": False}

    logger.debug("cursor_http POST %s/chat/completions model=%s messages=%d", base_url, model, len(messages))
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=body,
        )
        response.raise_for_status()
        data = response.json()
    logger.debug("cursor_http response status=%d content_length=%d", response.status_code, len(response.text))

    choices = data.get("choices") or []
    usage = data.get("usage") or {}
    content = ""
    if choices and len(choices) > 0:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            content = str(msg.get("content") or "")
        elif isinstance(msg, str):
            content = msg

    yield SystemMessage(subtype="init", data={"backend": "cursor_http"})
    yield AssistantMessage(content=[TextBlock(text=content)], model=model)
    yield ResultMessage(
        subtype="result",
        duration_ms=0,
        duration_api_ms=0,
        is_error=False,
        session_id=data.get("session_id") or "",
        usage=usage if isinstance(usage, dict) else None,
    )


def _patch_cursor_sdk_dash():
    """Strip trailing '-' from cursor-agent-sdk commands.

    Upstream cursor-agent-sdk appends '-' as a positional argument assuming
    the CLI interprets it as 'read from stdin'. The cursor-agent CLI treats
    it as a literal prompt instead. This patch removes '-' so the CLI falls
    back to reading the actual prompt from stdin.

    See: https://github.com/gitcnd/cursor-agent-sdk-python/issues/XXX
    """
    try:
        from cursor_agent_sdk.transport import SubprocessCLITransport
    except ImportError:
        return

    _original = SubprocessCLITransport._build_command

    def _patched(self):
        cmd = _original(self)
        if cmd and cmd[-1] == "-":
            cmd.pop()
        return cmd

    SubprocessCLITransport._build_command = _patched


_patch_cursor_sdk_dash()


async def _run_claude_cli(
    agent: AgentConfig,
    prompt: str,
    model: str,
    cwd: str,
    session_id: Optional[str] = None,
) -> AsyncIterator:
    """
    Run a query via the Claude CLI (claude --print).

    Uses the user's Claude subscription auth — no API key needed.
    Requires the `claude` CLI to be installed and logged in.
    """
    import asyncio

    cli_path = shutil.which("claude")
    if not cli_path:
        raise RuntimeError(
            "Claude CLI not found. Install it: npm install -g @anthropic-ai/claude-code\n"
            "Then login: claude (follow browser prompts)"
        )

    cmd = [cli_path, "--print", "--output-format", "json"]

    if model:
        cmd.extend(["--model", model])

    if agent.system_prompt:
        cmd.extend(["--system-prompt", agent.system_prompt])

    if session_id:
        cmd.extend(["--resume", session_id])

    # Permission mode
    if agent.permission_mode in ("acceptEdits", "bypassPermissions"):
        cmd.append("--dangerously-skip-permissions")

    # Add the prompt
    cmd.append(prompt)

    logger.info("claude-cli: %s model=%s cwd=%s prompt_len=%d", cli_path, model, cwd, len(prompt))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout_data, stderr_data = await proc.communicate()

    if proc.returncode != 0:
        error_text = stderr_data.decode("utf-8", errors="replace").strip()
        # Filter out SSL warnings
        error_lines = [l for l in error_text.splitlines() if "warn:" not in l.lower()]
        error_msg = "\n".join(error_lines) or f"Claude CLI exited with code {proc.returncode}"
        raise RuntimeError(f"Claude CLI error: {error_msg}")

    # Parse JSON output
    output = stdout_data.decode("utf-8", errors="replace").strip()
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        # Fallback: treat as plain text
        yield SystemMessage(subtype="init", data={"backend": "claude-cli"})
        yield AssistantMessage(content=[TextBlock(text=output)], model=model)
        yield ResultMessage(subtype="result", duration_ms=0, duration_api_ms=0,
                            is_error=False, session_id="", usage=None)
        return

    # Extract from JSON result
    result_text = data.get("result", "")
    sid = data.get("session_id", "")
    duration = data.get("duration_ms", 0)
    duration_api = data.get("duration_api_ms", 0)
    cost = data.get("total_cost_usd", 0)
    usage = data.get("usage", {})

    yield SystemMessage(subtype="init", data={
        "backend": "claude-cli",
        "session_id": sid,
        "cost_usd": cost,
    })
    yield AssistantMessage(content=[TextBlock(text=result_text)], model=model)
    yield ResultMessage(
        subtype="result",
        duration_ms=duration,
        duration_api_ms=duration_api,
        is_error=data.get("is_error", False),
        session_id=sid,
        usage=usage if isinstance(usage, dict) else None,
    )


async def run_agent(
    agent: AgentConfig,
    prompt: str,
    *,
    model_override: Optional[str] = None,
    cwd_override: Optional[str] = None,
    session_id: Optional[str] = None,
) -> AsyncIterator:
    """
    Run a query against the configured backend (cursor or claude) and
    yield SDK messages.  The caller iterates with `async for message in ...`.

    ``model_override`` is the **backend** model id (e.g. composer-1.5). The OpenAI API
    ``model`` field used to pick an agent by name must not be passed here—use ``None``
    so ``agent.model`` from YAML is used.

    Both SDKs expose identical APIs:
      - query(prompt, options) → AsyncIterator[Message]
      - *AgentOptions(model, cwd, permission_mode, extra_args, resume, system_prompt)
      - Same message types: SystemMessage, AssistantMessage, ResultMessage,
        TextBlock, ToolUseBlock, ToolResultBlock
    """
    import os

    model = model_override or agent.model
    cwd = cwd_override or agent.cwd

    logger.info(
        "run_agent START agent=%s backend=%s model=%s session=%s cwd=%s permission=%s",
        agent.name, agent.backend, model, session_id or "-", cwd, agent.permission_mode,
    )
    logger.debug(
        "run_agent details: system_prompt_len=%d extra_args=%s api_key=%s",
        len(agent.system_prompt or ""),
        list((agent.extra_args or {}).keys()),
        "set" if agent.api_key else "unset",
    )

    # Check for claude-cli override via environment
    backend = agent.backend
    if os.getenv("CODE_AGENTS_BACKEND", "").strip() == "claude-cli":
        backend = "claude-cli"
        model = model or os.getenv("CODE_AGENTS_CLAUDE_CLI_MODEL", "claude-sonnet-4-6")

    if backend == "claude-cli":
        async for message in _run_claude_cli(agent, prompt, model, cwd, session_id):
            yield message
        return

    if agent.backend == "cursor_http":
        async for message in _run_cursor_http(agent, prompt, model):
            yield message
        return

    # Headless path: avoid cursor-agent CLI (and desktop proxy) when an OpenAI-compatible base URL is set.
    if agent.backend == "cursor":
        _http_base = (agent.extra_args or {}).get("cursor_api_url") or os.getenv("CURSOR_API_URL")
        if _http_base and str(_http_base).strip():
            async for message in _run_cursor_http(agent, prompt, model):
                yield message
            return
        _http_only = os.getenv("CODE_AGENTS_HTTP_ONLY", "").strip().lower() in ("1", "true", "yes")
        if _http_only:
            raise RuntimeError(
                "CODE_AGENTS_HTTP_ONLY=1 but CURSOR_API_URL (or extra_args.cursor_api_url) is not set. "
                "Set CURSOR_API_URL in .env, or unset CODE_AGENTS_HTTP_ONLY to allow the cursor-agent CLI."
            )

    if agent.backend == "claude":
        from claude_agent_sdk import query as sdk_query
        from claude_agent_sdk import ClaudeAgentOptions as OptionsClass
        env_key = "ANTHROPIC_API_KEY"
    else:
        try:
            from cursor_agent_sdk import CursorAgentOptions as OptionsClass
            from cursor_agent_sdk import query as sdk_query
        except ImportError:
            raise RuntimeError(
                "cursor-agent-sdk is not installed (needed for the cursor-agent CLI). "
                "Install with: poetry install --with cursor — "
                "or set CURSOR_API_URL to use HTTP mode without the CLI."
            ) from None
        env_key = "CURSOR_API_KEY"

    env: dict[str, str] = {}
    api_key = agent.api_key or os.getenv(env_key)
    if api_key:
        env[env_key] = api_key

    # Inject --trust so cursor-agent doesn't prompt for workspace trust
    # Use deepcopy to avoid mutating the original agent config
    import copy as _copy
    extra = _copy.deepcopy(agent.extra_args or {})
    if agent.backend != "claude":
        extra.setdefault("trust", None)  # None = bare flag (--trust)

    options = OptionsClass(
        model=model,
        cwd=cwd,
        permission_mode=agent.permission_mode,
        extra_args=extra,
        resume=session_id,
        system_prompt=agent.system_prompt or None,
        env=env,
    )

    async for message in sdk_query(prompt=prompt, options=options):
        yield message
