from __future__ import annotations

import copy
import json
import logging
import os
import time
import uuid
from typing import Any, Optional

from .rules_loader import load_rules

logger = logging.getLogger(__name__)

from .backend import run_agent
from .config import AgentConfig
from .models import CompletionRequest, Message
from .openai_errors import format_process_error_message, unwrap_process_error

TOOL_RESULT_MAX_LINES = 30


# ── SSE helpers ──────────────────────────────────────────────────────────────

def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def make_chunk(
    cid: str,
    model: str,
    created: int,
    delta: dict,
    finish_reason: Optional[str] = None,
) -> str:
    return sse({
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "system_fingerprint": None,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
            "logprobs": None,
        }],
    })


# ── Formatting ───────────────────────────────────────────────────────────────

def _trim_to_tail(text: str, max_lines: int = TOOL_RESULT_MAX_LINES) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return f"... ({len(lines) - max_lines} lines omitted) ...\n" + "\n".join(lines[-max_lines:])


def format_tool_use(block: Any) -> str:
    args = json.dumps(block.input, indent=2) if isinstance(block.input, dict) else str(block.input)
    return f"\n\n> **Using tool: {block.name}**\n> ```json\n> {args}\n> ```\n\n"


def format_tool_result(block: Any) -> str:
    if isinstance(block.content, list):
        content = json.dumps(block.content, indent=2)
    elif isinstance(block.content, str):
        content = block.content
    else:
        content = str(block.content) if block.content else ""
    content = _trim_to_tail(content)
    return f"\n\n**Tool Result** (`{block.tool_use_id}`):\n```\n{content}\n```\n\n"


def last_user_message(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.role == "user" and m.content:
            return m.content
    return ""


def build_prompt(messages: list[Message]) -> str:
    """Build a prompt from messages.

    If there are multiple user/assistant turns, pack the full conversation
    history into a single prompt so the SDK has full context — even if
    the session_id expired. Single-turn requests just use the last user
    message directly.
    """
    non_system = [m for m in messages if m.role != "system"]
    if len(non_system) > 1:
        parts = []
        for m in non_system:
            label = "Human" if m.role == "user" else "Assistant"
            parts.append(f"{label}: {m.content}")
        return "\n\n".join(parts)
    return last_user_message(messages)


# ── Streaming response ──────────────────────────────────────────────────────

async def stream_response(agent: AgentConfig, req: CompletionRequest):
    """
    Async generator that yields OpenAI-compliant SSE chunks.

    Tool activity (ToolUseBlock / ToolResultBlock) is rendered as:
      - reasoning_content delta   when stream_tool_activity=True
      - silently consumed         when stream_tool_activity=False

    Session ID is returned in the final chunk when include_session=True.
    """
    cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    model = req.model or agent.model
    prompt = build_prompt(req.messages)

    # Inject rules into agent system prompt (fresh from disk every request)
    rules_text = load_rules(agent.name, req.cwd or os.getenv("TARGET_REPO_PATH"))
    if rules_text:
        agent = copy.deepcopy(agent)
        agent.system_prompt = f"{rules_text}\n\n{agent.system_prompt or ''}"

    show_tools = req.stream_tool_activity if req.stream_tool_activity is not None else agent.stream_tool_activity
    show_session = req.include_session if req.include_session is not None else agent.include_session

    captured_session_id: Optional[str] = None
    chunk_count = 0
    text_bytes = 0
    tool_calls = 0
    start_time = time.time()

    logger.info(
        "[%s] stream_response START agent=%s model=%s prompt_len=%d messages=%d session=%s",
        cid, agent.name, model, len(prompt), len(req.messages), req.session_id or "-",
    )
    logger.debug("[%s] prompt_preview=%r", cid, prompt[:200])

    # OpenAI-compatible clients expect an initial chunk before backend work.
    yield make_chunk(cid, model, created, {"role": "assistant", "content": ""})

    try:
        async for message in run_agent(
            agent,
            prompt,
            model_override=None,
            cwd_override=req.cwd,
            session_id=req.session_id,
        ):
            if type(message).__name__ == "SystemMessage" and getattr(message, "subtype", None) == "init":
                sid = message.data.get("session_id")
                if sid:
                    captured_session_id = sid
                logger.debug("[%s] SystemMessage init session=%s", cid, sid or "-")

            elif type(message).__name__ == "AssistantMessage":
                for block in message.content:
                    if type(block).__name__ == "TextBlock" and getattr(block, "text", None):
                        chunk_count += 1
                        text_bytes += len(block.text)
                        yield make_chunk(cid, model, created, {"content": block.text})

                    elif type(block).__name__ == "ToolUseBlock":
                        tool_calls += 1
                        logger.info("[%s] ToolUse: %s (id=%s)", cid, block.name, getattr(block, "id", "-"))
                        logger.debug("[%s] ToolUse input: %s", cid, str(getattr(block, "input", ""))[:500])
                        if show_tools:
                            yield make_chunk(cid, model, created, {
                                "reasoning_content": format_tool_use(block),
                            })

                    elif type(block).__name__ == "ToolResultBlock":
                        content_preview = str(getattr(block, "content", ""))[:200]
                        logger.info("[%s] ToolResult: id=%s len=%d", cid, getattr(block, "tool_use_id", "-"), len(str(getattr(block, "content", ""))))
                        logger.debug("[%s] ToolResult preview: %s", cid, content_preview)
                        if show_tools:
                            yield make_chunk(cid, model, created, {
                                "reasoning_content": format_tool_result(block),
                            })

            elif type(message).__name__ == "ResultMessage":
                if message.session_id:
                    captured_session_id = message.session_id
                elapsed = time.time() - start_time
                logger.info(
                    "[%s] stream_response DONE agent=%s chunks=%d text_bytes=%d tool_calls=%d elapsed=%.1fs session=%s",
                    cid, agent.name, chunk_count, text_bytes, tool_calls, elapsed, captured_session_id or "-",
                )
                if hasattr(message, "usage") and message.usage:
                    logger.info("[%s] usage: %s", cid, message.usage)

                final_chunk: dict[str, Any] = {
                    "id": cid,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "system_fingerprint": None,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                        "logprobs": None,
                    }],
                }
                if show_session and captured_session_id:
                    final_chunk["session_id"] = captured_session_id
                # Include usage data in final chunk for client-side token tracking
                if hasattr(message, "usage") and message.usage:
                    final_chunk["usage"] = message.usage
                if hasattr(message, "duration_ms"):
                    final_chunk["duration_ms"] = message.duration_ms

                yield sse(final_chunk)
                yield "data: [DONE]\n\n"
                return

        final: dict[str, Any] = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "system_fingerprint": None,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
                "logprobs": None,
            }],
        }
        if show_session and captured_session_id:
            final["session_id"] = captured_session_id
        yield sse(final)
    except Exception as e:
        logger.exception("Stream error from agent backend")
        pe = unwrap_process_error(e)
        err_text = format_process_error_message(pe) if pe is not None else str(e)
        final_err: dict[str, Any] = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "system_fingerprint": None,
            "choices": [{
                "index": 0,
                "delta": {"content": f"\n[Error: {err_text}]"},
                "finish_reason": "stop",
                "logprobs": None,
            }],
        }
        if show_session and captured_session_id:
            final_err["session_id"] = captured_session_id
        yield sse(final_err)
    yield "data: [DONE]\n\n"


# ── Non-streaming response ──────────────────────────────────────────────────

async def collect_response(agent: AgentConfig, req: CompletionRequest) -> dict:
    cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    model = req.model or agent.model
    prompt = build_prompt(req.messages)

    # Inject rules into agent system prompt (fresh from disk every request)
    rules_text = load_rules(agent.name, req.cwd or os.getenv("TARGET_REPO_PATH"))
    if rules_text:
        agent = copy.deepcopy(agent)
        agent.system_prompt = f"{rules_text}\n\n{agent.system_prompt or ''}"

    show_tools = req.stream_tool_activity if req.stream_tool_activity is not None else agent.stream_tool_activity
    show_session = req.include_session if req.include_session is not None else agent.include_session

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    captured_session_id: Optional[str] = None
    usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    tool_calls = 0
    start_time = time.time()

    logger.info(
        "[%s] collect_response START agent=%s model=%s prompt_len=%d messages=%d session=%s",
        cid, agent.name, model, len(prompt), len(req.messages), req.session_id or "-",
    )
    logger.debug("[%s] prompt_preview=%r", cid, prompt[:200])

    async for message in run_agent(
        agent,
        prompt,
        model_override=None,
        cwd_override=req.cwd,
        session_id=req.session_id,
    ):
        if type(message).__name__ == "SystemMessage" and getattr(message, "subtype", None) == "init":
            sid = message.data.get("session_id")
            if sid:
                captured_session_id = sid
            logger.debug("[%s] SystemMessage init session=%s", cid, sid or "-")

        elif type(message).__name__ == "AssistantMessage":
            for block in message.content:
                if type(block).__name__ == "TextBlock" and getattr(block, "text", None):
                    content_parts.append(block.text)

                elif type(block).__name__ == "ToolUseBlock":
                    tool_calls += 1
                    logger.info("[%s] ToolUse: %s (id=%s)", cid, block.name, getattr(block, "id", "-"))
                    logger.debug("[%s] ToolUse input: %s", cid, str(getattr(block, "input", ""))[:500])
                    if show_tools:
                        reasoning_parts.append(format_tool_use(block))

                elif type(block).__name__ == "ToolResultBlock":
                    logger.info("[%s] ToolResult: id=%s len=%d", cid, getattr(block, "tool_use_id", "-"), len(str(getattr(block, "content", ""))))
                    if show_tools:
                        reasoning_parts.append(format_tool_result(block))

        elif type(message).__name__ == "ResultMessage":
            if message.session_id:
                captured_session_id = message.session_id
            elapsed = time.time() - start_time
            logger.info(
                "[%s] collect_response DONE agent=%s content_len=%d tool_calls=%d elapsed=%.1fs session=%s",
                cid, agent.name, sum(len(p) for p in content_parts), tool_calls, elapsed, captured_session_id or "-",
            )
            if message.usage:
                usage = {
                    "prompt_tokens": message.usage.get("prompt_tokens", 0),
                    "completion_tokens": message.usage.get("completion_tokens", 0),
                    "total_tokens": message.usage.get("total_tokens", 0),
                }

    msg: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(content_parts) or "",
    }
    if reasoning_parts:
        msg["reasoning_content"] = "".join(reasoning_parts)

    response: dict[str, Any] = {
        "id": cid,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "system_fingerprint": None,
        "choices": [{
            "index": 0,
            "message": msg,
            "finish_reason": "stop",
            "logprobs": None,
        }],
        "usage": usage,
    }

    if show_session and captured_session_id:
        response["session_id"] = captured_session_id

    return response
