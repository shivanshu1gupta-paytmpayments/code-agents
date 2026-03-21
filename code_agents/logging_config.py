"""
Centralized logging configuration for Code Agents.

Set LOG_LEVEL env var to control verbosity:
  LOG_LEVEL=DEBUG   — full request/response bodies, backend calls, tool activity
  LOG_LEVEL=INFO    — startup, requests, agent routing (default)
  LOG_LEVEL=WARNING — only problems

Logs are written to both stderr and logs/code-agents.log.
The current log file contains only the last hour of data.
Every hour, the file is rotated to a timestamped backup:
  logs/code-agents.log.2026-03-21_14  (kept for 7 days = 168 hourly files)
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path


def _ensure_log_dir() -> Path:
    """Create the logs directory relative to the project root and return the log file path."""
    # Project root is two levels up from this file: code_agents/logging_config.py → code_agents/ → project/
    project_root = Path(__file__).resolve().parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / "code-agents.log"


def setup_logging() -> None:
    """Configure logging for the entire application. Call once at startup."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # Detailed format: timestamp with ms, level, logger, function, message
    fmt = (
        "%(asctime)s.%(msecs)03d %(levelname)-8s [%(name)s:%(funcName)s:%(lineno)d] %(message)s"
    )
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    # Reset any existing handlers (e.g. uvicorn's defaults)
    root = logging.getLogger()
    root.handlers.clear()

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # File handler — hourly rotation
    # Current file: logs/code-agents.log (only last hour of data)
    # Backups:      logs/code-agents.log.2026-03-21_14, ...
    # Kept for 7 days (168 hourly files)
    try:
        log_file = _ensure_log_dir()
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_file,
            when="H",           # Rotate every hour
            interval=1,         # Every 1 hour
            backupCount=168,    # Keep 7 days of hourly backups (24 * 7)
            encoding="utf-8",
            utc=False,          # Use local time for backup filenames
        )
        # Backup filenames: code-agents.log.2026-03-21_14
        file_handler.suffix = "%Y-%m-%d_%H"
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as e:
        # If we can't write logs to file, warn but don't crash
        root.warning("Could not set up file logging at logs/code-agents.log: %s", e)

    root.setLevel(level)

    # Quiet down noisy third-party loggers unless we're at DEBUG
    if level > logging.DEBUG:
        for name in ("uvicorn.access", "httpx", "httpcore", "urllib3", "elasticsearch"):
            logging.getLogger(name).setLevel(logging.WARNING)

    # Uvicorn's own loggers — let them through at INFO+ so startup banner shows
    logging.getLogger("uvicorn").setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)

    # Log the logging config itself for traceability
    startup_logger = logging.getLogger("code_agents.logging")
    startup_logger.info(
        "Logging initialized: level=%s, file=%s, rotation=hourly, backups=168 (7 days)",
        level_name,
        _ensure_log_dir(),
    )
