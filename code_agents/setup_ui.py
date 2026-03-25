"""Setup UI helpers — colors, prompts, validators."""

from __future__ import annotations

import getpass
import re
import sys
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# ANSI color helpers
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty()


def _wrap(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


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
# Prompts
# ---------------------------------------------------------------------------

def prompt(
    label: str,
    default: Optional[str] = None,
    secret: bool = False,
    required: bool = False,
    validator: Optional[Callable[[str], bool]] = None,
    transform: Optional[Callable[[str], str]] = None,
    error_msg: str = "Invalid input.",
) -> str:
    """Prompt user for input. Loops on validation failure. Optional transform."""
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
        if value and transform:
            value = transform(value)
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
        print(red("    Enter y or n."))


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
            idx = int(value)
            if 1 <= idx <= len(choices):
                return idx
        except ValueError:
            pass
        print(red(f"    Enter a number 1-{len(choices)}."))


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def validate_url(v: str) -> bool:
    try:
        result = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(v)
        return bool(result.scheme and result.netloc)
    except Exception:
        return False


def validate_port(v: str) -> bool:
    try:
        return 1 <= int(v) <= 65535
    except ValueError:
        return False


def validate_job_path(v: str) -> bool:
    """Jenkins job should be a clean folder path, not a full URL."""
    if v.startswith("http://") or v.startswith("https://"):
        return False
    return bool(v.strip("/"))


def clean_job_path(v: str) -> str:
    """Strip 'job/' prefixes from Jenkins paths."""
    raw_parts = [p for p in v.strip("/").split("/") if p]
    parts = []
    for i, p in enumerate(raw_parts):
        if p == "job" and i + 1 < len(raw_parts):
            continue
        else:
            parts.append(p)
    cleaned = "/".join(parts)
    if cleaned != v.strip("/"):
        print(dim(f"    Auto-cleaned: {v} → {cleaned}"))
    return cleaned
