"""Chat UI helpers — colors, spinners, selectors, markdown, welcome boxes."""

from __future__ import annotations

import os
import re
import sys
from typing import Optional

# ---------------------------------------------------------------------------
# Colors (same as setup.py, no deps)
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty()


def _w(code: str, t: str) -> str:
    return f"\033[{code}m{t}\033[0m" if _USE_COLOR else t


def bold(t: str) -> str: return _w("1", t)
def green(t: str) -> str: return _w("32", t)
def yellow(t: str) -> str: return _w("33", t)
def red(t: str) -> str: return _w("31", t)
def cyan(t: str) -> str: return _w("36", t)
def dim(t: str) -> str: return _w("2", t)
def magenta(t: str) -> str: return _w("35", t)


def _rl_wrap(code: str, t: str) -> str:
    """Wrap ANSI escape in readline invisible markers for prompts."""
    if not _USE_COLOR:
        return t
    return f"\x01\033[{code}m\x02{t}\x01\033[0m\x02"


def _rl_bold(t: str) -> str: return _rl_wrap("1", t)
def _rl_green(t: str) -> str: return _rl_wrap("32", t)


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

_ANSI_STRIP_RE = re.compile(r"\033\[[0-9;]*m")


def _visible_len(text: str) -> int:
    """Return the visible length of a string, ignoring ANSI escape codes."""
    return len(_ANSI_STRIP_RE.sub("", text))


def _render_markdown(text: str) -> str:
    """Render basic markdown to terminal ANSI: **bold**, `code`, ## headers."""
    if not _USE_COLOR:
        return text
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: bold(m.group(1)), text)
    text = re.sub(r'`([^`]+)`', lambda m: cyan(m.group(1)), text)
    text = re.sub(r'^(#{1,4})\s+(.+)$', lambda m: bold(m.group(2)), text, flags=re.MULTILINE)
    return text


# ---------------------------------------------------------------------------
# Spinner
# ---------------------------------------------------------------------------

def _spinner(message: str):
    """Context manager that shows a spinner while waiting."""
    import threading
    import itertools

    stop_event = threading.Event()

    def _spin():
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        for frame in itertools.cycle(frames):
            if stop_event.is_set():
                break
            sys.stdout.write(f"\r  {yellow(frame)} {dim(message)}")
            sys.stdout.flush()
            stop_event.wait(0.1)
        sys.stdout.write(f"\r{' ' * (len(message) + 10)}\r")
        sys.stdout.flush()

    class _SpinnerCtx:
        def __enter__(self):
            self._thread = threading.Thread(target=_spin, daemon=True)
            self._thread.start()
            return self

        def __exit__(self, *args):
            stop_event.set()
            self._thread.join(timeout=1)

    return _SpinnerCtx()


# ---------------------------------------------------------------------------
# Interactive selectors
# ---------------------------------------------------------------------------

def _ask_yes_no(prompt_text: str, default: bool = True) -> bool:
    """Interactive Yes/No prompt with Tab switching."""
    return _tab_selector(prompt_text, ["Yes", "No"], default=0 if default else 1) == 0


def _tab_selector(prompt_text: str, options: list[str], default: int = 0) -> int:
    """
    Interactive selector with Tab to cycle. Press Enter to confirm.
    Returns the index of the selected option.
    """
    selected = default

    def _render():
        parts = []
        for i, opt in enumerate(options):
            if i == selected:
                parts.append(bold(green(f"❯ {opt}")))
            else:
                parts.append(dim(f"  {opt}"))
        line = "    ".join(parts)
        sys.stdout.write(f"\r  {line}  {dim('(Tab=switch, Enter=confirm)')}")
        sys.stdout.flush()

    print(f"  {bold(prompt_text)}")
    _render()

    try:
        import tty
        import termios
        import signal

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        def _restore(signum=None, frame=None):
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                pass

        old_sigint = signal.signal(signal.SIGINT, _restore)
        old_sigterm = signal.signal(signal.SIGTERM, _restore)

        try:
            while True:
                tty.setraw(fd)
                try:
                    ch = sys.stdin.read(1)
                except Exception:
                    break
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

                if not ch or ch == '\x03':  # Ctrl+C or EOF
                    print()
                    return len(options) - 1

                if ch == '\t':
                    selected = (selected + 1) % len(options)
                    _render()
                elif ch == '\r' or ch == '\n':
                    break
                elif ch == '\x1b':
                    # Arrow keys: read remaining bytes (non-raw now)
                    tty.setraw(fd)
                    try:
                        ch2 = sys.stdin.read(1)
                        if ch2 == '[':
                            ch3 = sys.stdin.read(1)
                            if ch3 in ('C', 'D'):
                                selected = (selected + 1) % len(options)
                    except Exception:
                        pass
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    _render()
        finally:
            _restore()
            signal.signal(signal.SIGINT, old_sigint)
            signal.signal(signal.SIGTERM, old_sigterm)
    except (ImportError, OSError, ValueError):
        print()
        for i, opt in enumerate(options):
            print(f"    {bold(str(i + 1) + '.')} {opt}")
        try:
            answer = input(f"  {dim(f'Choose [1-{len(options)}]')}: ").strip()
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                selected = int(answer) - 1
        except (EOFError, KeyboardInterrupt):
            selected = len(options) - 1

    print()
    return selected


# ---------------------------------------------------------------------------
# Welcome message
# ---------------------------------------------------------------------------

# Import AGENT_WELCOME from chat_data to avoid circular imports
def _print_welcome(agent_name: str, agent_welcome: dict) -> None:
    """Print agent welcome message in a red bordered box."""
    import shutil

    welcome = agent_welcome.get(agent_name)
    if not welcome:
        return

    title, capabilities, examples = welcome
    term_width = shutil.get_terminal_size((80, 24)).columns
    box_width = min(term_width - 4, 80)
    inner = box_width - 2

    def _pad(text: str) -> str:
        vis = _visible_len(text)
        pad = max(0, inner - vis - 1)
        return red(f"  │") + f" {text}{' ' * pad}" + red("│")

    print(red(f"  ┌{'─' * box_width}┐"))
    title_styled = f" {bold(cyan(title))}"
    title_pad = max(0, inner - len(title) - 1)
    print(red(f"  │") + title_styled + " " * title_pad + red("│"))
    print(red(f"  ├{'─' * box_width}┤"))
    print(_pad(""))
    print(_pad(bold("What I can do:")))
    for cap in capabilities:
        print(_pad(f"  • {cap}"))
    print(_pad(""))
    print(_pad(bold("Try asking:")))
    for ex in examples:
        print(_pad(f"  {dim(ex)}"))
    print(_pad(""))
    print(red(f"  └{'─' * box_width}┘"))
    print()
