"""
Chat history persistence for Code Agents.

Saves and loads chat sessions as JSON files in ~/.code-agents/chat_history/.
Each session tracks: agent, repo, messages, timestamps, and a title derived
from the first user message.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional


HISTORY_DIR = Path.home() / ".code-agents" / "chat_history"


def _ensure_dir() -> Path:
    """Ensure the chat history directory exists."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return HISTORY_DIR


def _session_path(session_id: str) -> Path:
    """Return the file path for a given session ID."""
    return _ensure_dir() / f"{session_id}.json"


def _make_title(text: str, max_len: int = 60) -> str:
    """Derive a short title from the first user message."""
    # Take first line, strip whitespace
    line = text.strip().splitlines()[0].strip() if text.strip() else "Untitled"
    if len(line) > max_len:
        line = line[:max_len - 3] + "..."
    return line


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


def create_session(
    agent_name: str,
    repo_path: str,
    session_id: Optional[str] = None,
) -> dict:
    """Create a new chat session and persist it. Returns the session dict."""
    sid = session_id or str(uuid.uuid4())
    now = time.time()
    session = {
        "id": sid,
        "agent": agent_name,
        "repo_path": repo_path,
        "title": "New chat",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    _save(session)
    return session


def _save(session: dict) -> None:
    """Write session dict to disk."""
    path = _session_path(session["id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


def load_session(session_id: str) -> Optional[dict]:
    """Load a session by ID. Returns None if not found."""
    path = _session_path(session_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def add_message(session: dict, role: str, content: str) -> None:
    """Append a message to the session and persist."""
    session["messages"].append({
        "role": role,
        "content": content,
        "timestamp": time.time(),
    })
    session["updated_at"] = time.time()

    # Auto-set title from first user message
    if role == "user" and session.get("title") == "New chat":
        session["title"] = _make_title(content)

    _save(session)


def list_sessions(limit: int = 20, repo_path: Optional[str] = None) -> list[dict]:
    """
    List recent sessions, sorted by updated_at descending.

    Returns lightweight dicts with: id, agent, title, updated_at, repo_path, message_count.
    Optionally filter by repo_path.
    """
    history_dir = _ensure_dir()
    sessions = []

    for f in history_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue

        if repo_path and data.get("repo_path") != repo_path:
            continue

        sessions.append({
            "id": data.get("id", f.stem),
            "agent": data.get("agent", "?"),
            "title": data.get("title", "Untitled"),
            "updated_at": data.get("updated_at", 0),
            "repo_path": data.get("repo_path", ""),
            "message_count": len(data.get("messages", [])),
        })

    sessions.sort(key=lambda s: s["updated_at"], reverse=True)
    return sessions[:limit]


def delete_session(session_id: str) -> bool:
    """Delete a session file. Returns True if deleted."""
    path = _session_path(session_id)
    if path.exists():
        path.unlink()
        return True
    return False
