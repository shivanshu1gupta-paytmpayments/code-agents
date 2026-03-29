"""
Token usage tracking — per message, session, day, month.

Writes to CSV at ~/.code-agents/token_usage.csv for analysis.
Tracks: backend, model, agent, input_tokens, output_tokens, cost, timestamp.
"""

from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

USAGE_CSV_PATH = Path.home() / ".code-agents" / "token_usage.csv"

CSV_HEADERS = [
    "timestamp", "date", "month", "year", "session_id", "agent",
    "backend", "model", "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens",
    "total_tokens", "cost_usd", "duration_ms",
]


@dataclass
class SessionUsage:
    """Tracks token usage for a terminal session."""
    session_id: str = ""
    agent: str = ""
    backend: str = ""
    model: str = ""
    messages: int = 0
    total_input: int = 0
    total_output: int = 0
    total_cache_read: int = 0
    total_cache_write: int = 0
    total_cost: float = 0.0
    total_duration_ms: int = 0
    start_time: float = field(default_factory=time.monotonic)


# Global session tracker (reset per terminal session)
_current_session = SessionUsage()


def init_session(session_id: str = "", agent: str = "", backend: str = "", model: str = "") -> None:
    """Initialize tracking for a new terminal session."""
    global _current_session
    _current_session = SessionUsage(
        session_id=session_id,
        agent=agent,
        backend=backend,
        model=model,
    )


def record_usage(
    agent: str,
    backend: str,
    model: str,
    usage: dict | None,
    cost_usd: float = 0.0,
    duration_ms: int = 0,
    session_id: str = "",
) -> None:
    """Record token usage for a single message. Appends to CSV and updates session totals."""
    if not usage:
        return

    input_tokens = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0
    cache_read = usage.get("cache_read_input_tokens", 0) or 0
    cache_write = usage.get("cache_creation_input_tokens", 0) or 0
    total = input_tokens + output_tokens

    # Update session totals
    _current_session.messages += 1
    _current_session.total_input += input_tokens
    _current_session.total_output += output_tokens
    _current_session.total_cache_read += cache_read
    _current_session.total_cache_write += cache_write
    _current_session.total_cost += cost_usd
    _current_session.total_duration_ms += duration_ms
    if agent:
        _current_session.agent = agent
    if backend:
        _current_session.backend = backend
    if model:
        _current_session.model = model

    # Write to CSV
    now = datetime.now()
    row = {
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "month": now.strftime("%Y-%m"),
        "year": now.strftime("%Y"),
        "session_id": session_id or _current_session.session_id,
        "agent": agent,
        "backend": backend,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "total_tokens": total,
        "cost_usd": f"{cost_usd:.6f}" if cost_usd else "0",
        "duration_ms": duration_ms,
    }

    _append_csv(row)


def _append_csv(row: dict) -> None:
    """Append a row to the usage CSV. Creates file with headers if missing."""
    USAGE_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_exists = USAGE_CSV_PATH.is_file()

    try:
        with open(USAGE_CSV_PATH, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except OSError:
        pass  # silently skip if can't write


def get_session_summary() -> dict:
    """Get current terminal session usage summary."""
    elapsed = time.monotonic() - _current_session.start_time
    return {
        "messages": _current_session.messages,
        "input_tokens": _current_session.total_input,
        "output_tokens": _current_session.total_output,
        "cache_read_tokens": _current_session.total_cache_read,
        "cache_write_tokens": _current_session.total_cache_write,
        "total_tokens": _current_session.total_input + _current_session.total_output,
        "cost_usd": _current_session.total_cost,
        "duration_ms": _current_session.total_duration_ms,
        "session_seconds": elapsed,
        "agent": _current_session.agent,
        "backend": _current_session.backend,
        "model": _current_session.model,
    }


def get_daily_summary(date: str | None = None) -> dict:
    """Get token usage for a specific date (default: today). Reads from CSV."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    return _aggregate_csv("date", date)


def get_monthly_summary(month: str | None = None) -> dict:
    """Get token usage for a specific month (default: this month). Reads from CSV."""
    if month is None:
        month = datetime.now().strftime("%Y-%m")
    return _aggregate_csv("month", month)


def get_yearly_summary(year: str | None = None) -> dict:
    """Get token usage for a specific year (default: this year)."""
    if year is None:
        year = datetime.now().strftime("%Y")
    return _aggregate_csv("year", year)


def get_all_time_summary() -> dict:
    """Get total token usage across all time."""
    return _aggregate_csv(None, None)


def get_model_breakdown(date: str | None = None) -> list[dict]:
    """Get token usage broken down by backend + model."""
    if not USAGE_CSV_PATH.is_file():
        return []

    breakdown: dict[str, dict] = {}
    try:
        with open(USAGE_CSV_PATH, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if date and row.get("date") != date:
                    continue
                key = f"{row.get('backend', '?')} / {row.get('model', '?')}"
                if key not in breakdown:
                    breakdown[key] = {
                        "backend": row.get("backend", ""),
                        "model": row.get("model", ""),
                        "messages": 0, "input_tokens": 0, "output_tokens": 0,
                        "total_tokens": 0, "cost_usd": 0.0,
                    }
                b = breakdown[key]
                b["messages"] += 1
                b["input_tokens"] += int(row.get("input_tokens", 0) or 0)
                b["output_tokens"] += int(row.get("output_tokens", 0) or 0)
                b["total_tokens"] += int(row.get("total_tokens", 0) or 0)
                b["cost_usd"] += float(row.get("cost_usd", 0) or 0)
    except (OSError, csv.Error):
        pass

    return sorted(breakdown.values(), key=lambda x: x["total_tokens"], reverse=True)


def _aggregate_csv(filter_field: str | None, filter_value: str | None) -> dict:
    """Aggregate token usage from CSV, optionally filtered."""
    result = {
        "messages": 0, "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_write_tokens": 0,
        "total_tokens": 0, "cost_usd": 0.0,
    }

    if not USAGE_CSV_PATH.is_file():
        return result

    try:
        with open(USAGE_CSV_PATH, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if filter_field and row.get(filter_field) != filter_value:
                    continue
                result["messages"] += 1
                result["input_tokens"] += int(row.get("input_tokens", 0) or 0)
                result["output_tokens"] += int(row.get("output_tokens", 0) or 0)
                result["cache_read_tokens"] += int(row.get("cache_read_tokens", 0) or 0)
                result["cache_write_tokens"] += int(row.get("cache_write_tokens", 0) or 0)
                result["total_tokens"] += int(row.get("total_tokens", 0) or 0)
                result["cost_usd"] += float(row.get("cost_usd", 0) or 0)
    except (OSError, csv.Error):
        pass

    return result