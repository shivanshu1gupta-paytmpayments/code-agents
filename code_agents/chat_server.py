"""Chat server communication — health check, agent list, streaming."""

from __future__ import annotations

import json
import os
import sys
from typing import Optional


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


def _check_workspace_trust(repo_path: str) -> bool:
    """Lightweight workspace trust check — no slow subprocess calls."""
    if os.getenv("CODE_AGENTS_BACKEND", "").strip() == "claude-cli":
        return True
    if os.getenv("CURSOR_API_URL", "").strip():
        return True
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        return True
    import shutil
    from .chat_ui import yellow, dim
    if not shutil.which("cursor-agent"):
        print(yellow("  ! cursor-agent not found — Cursor backend may not work"))
        print(dim("    Install cursor-agent or set CODE_AGENTS_BACKEND=claude-cli"))
        print()
    return True


def _get_agents(url: str) -> dict[str, str]:
    """Fetch agent list from server. Returns {name: display_name}."""
    import httpx
    try:
        r = httpx.get(f"{url}/v1/agents", timeout=5.0)
        data = r.json()
        if isinstance(data, dict):
            agents = data.get("data") or data.get("agents") or []
        elif isinstance(data, list):
            agents = data
        else:
            agents = []
        return {a.get("name", "?"): a.get("display_name", "") for a in agents if isinstance(a, dict)}
    except Exception:
        return {}


def _stream_chat(
    url: str,
    agent: str,
    messages: list[dict],
    session_id: Optional[str] = None,
    cwd: Optional[str] = None,
):
    """Send a chat request with streaming and yield response pieces."""
    import httpx

    body: dict = {
        "messages": messages,
        "stream": True,
        "include_session": True,
        "stream_tool_activity": True,
    }
    if session_id:
        body["session_id"] = session_id
    if cwd:
        body["cwd"] = cwd

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
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

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
