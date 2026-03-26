"""Chat command execution — extract, resolve placeholders, run, and offer commands."""

from __future__ import annotations

import fcntl
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .chat_ui import (
    bold, green, yellow, red, cyan, dim,
    _visible_len, _tab_selector,
)

# ---------------------------------------------------------------------------
# Command extraction from agent responses
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(
    r"```(?:bash|sh|shell|zsh|console)\s*\n(.*?)```",
    re.DOTALL,
)


def _extract_commands(text: str) -> list[str]:
    """Extract shell commands from markdown code blocks in agent response.

    Handles multi-line commands joined with backslash continuations.
    """
    commands = []
    for match in _CODE_BLOCK_RE.finditer(text):
        block = match.group(1).strip()
        lines = block.splitlines()
        joined_lines: list[str] = []
        current = ""
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                if current:
                    joined_lines.append(current)
                    current = ""
                continue
            if current:
                current += " " + stripped
            else:
                if stripped.startswith("$ "):
                    stripped = stripped[2:]
                elif stripped.startswith("> "):
                    stripped = stripped[2:]
                current = stripped

            if current.endswith("\\"):
                current = current[:-1].rstrip()
            else:
                joined_lines.append(current)
                current = ""

        if current:
            joined_lines.append(current)

        for cmd in joined_lines:
            if cmd:
                commands.append(cmd)
    return commands


# ---------------------------------------------------------------------------
# Placeholder resolution
# ---------------------------------------------------------------------------

_PLACEHOLDER_ANGLE_RE = re.compile(r"<([A-Z][A-Z0-9_]+)>")
_PLACEHOLDER_CURLY_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def _resolve_placeholders(cmd: str) -> Optional[str]:
    """Detect placeholder tokens and prompt user to fill them."""
    found: list[tuple[str, str]] = []
    for m in _PLACEHOLDER_ANGLE_RE.finditer(cmd):
        found.append((m.group(0), m.group(1)))
    for m in _PLACEHOLDER_CURLY_RE.finditer(cmd):
        found.append((m.group(0), m.group(1)))

    if not found:
        return cmd

    seen = set()
    unique: list[tuple[str, str]] = []
    for token, name in found:
        if token not in seen:
            seen.add(token)
            unique.append((token, name))

    print(f"    {yellow('Placeholders detected — fill in values:')}")
    replacements = {}
    for token, name in unique:
        try:
            value = input(f"    {bold(token)}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not value:
            print(dim(f"    Skipped (no value for {token})."))
            return None
        replacements[token] = value

    for token, value in replacements.items():
        cmd = cmd.replace(token, value)

    return cmd


# ---------------------------------------------------------------------------
# Command trust (saved in rules)
# ---------------------------------------------------------------------------

def _save_command_to_rules(cmd: str, agent_name: str, repo_path: str) -> None:
    """Save an executed command to the agent's project rules file (file-locked)."""
    from .rules_loader import PROJECT_RULES_DIRNAME
    rules_dir = Path(repo_path) / PROJECT_RULES_DIRNAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / f"{agent_name}.md"

    try:
        with open(str(rules_file), "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                existing = f.read()
                if cmd in existing:
                    print(dim("  (command already in rules)"))
                    return
                if "## Saved Commands" not in existing:
                    f.write("\n\n## Saved Commands\nThese commands have been approved and can be auto-run.\n")
                f.write(f"\n```bash\n{cmd}\n```\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        print(green(f"  ✓ Saved to {rules_file}"))
    except OSError as e:
        print(yellow(f"  ! Could not save to rules: {e}"))


def _is_command_trusted(cmd: str, agent_name: str, repo_path: str) -> bool:
    """Check if a command is in the agent's saved/trusted commands (file-locked)."""
    from .rules_loader import PROJECT_RULES_DIRNAME
    rules_file = Path(repo_path) / PROJECT_RULES_DIRNAME / f"{agent_name}.md"
    if not rules_file.is_file():
        return False
    try:
        with open(str(rules_file), "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                content = f.read()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return cmd in content
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Run a single command
# ---------------------------------------------------------------------------

def _run_single_command(cmd: str, cwd: str) -> str:
    """Run a single shell command, display in red box, and return raw output."""
    import shutil
    import threading
    import time as _cmd_time

    print(f"  {bold(green('● BASH'))} {dim('running...')}")

    term_width = shutil.get_terminal_size((80, 24)).columns
    box_width = min(term_width - 4, 100)
    inner_width = box_width - 2

    def _box_line(text: str) -> str:
        visible = text[:inner_width]
        pad = max(0, inner_width - len(visible))
        return red(f"  │") + f" {visible}{' ' * pad}" + red("│")

    # Top border + command (wrapped)
    import textwrap
    print(red(f"  ┌{'─' * box_width}┐"))
    cmd_lines = textwrap.wrap(cmd, width=inner_width - 3)
    for idx, line in enumerate(cmd_lines):
        if idx == 0:
            prefix = f" {bold('$')} {cyan(line)}"
            vis_len = len(f" $ {line}")
        else:
            prefix = f"   {cyan(line)}"
            vis_len = len(f"   {line}")
        pad = max(0, inner_width - vis_len)
        print(red(f"  │") + prefix + " " * pad + red("│"))
    print(red(f"  ├{'─' * box_width}┤"))

    raw_output = ""
    try:
        proc = subprocess.Popen(
            cmd, shell=True, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        _cmd_start = _cmd_time.monotonic()
        _cmd_done = threading.Event()
        _is_jenkins = "jenkins" in cmd.lower() and ("build" in cmd.lower() or "wait" in cmd.lower())

        def _poll_jenkins_status() -> str:
            try:
                import httpx
                from .chat_server import _server_url
                r = httpx.get(f"{_server_url()}/health", timeout=2.0)
                if r.status_code != 200:
                    return ""
                build_job = os.getenv("JENKINS_BUILD_JOB", "")
                if build_job:
                    r = httpx.get(f"{_server_url()}/jenkins/build/{build_job}/last", timeout=5.0)
                    if r.status_code == 200:
                        data = r.json()
                        building = data.get("building", False)
                        result = data.get("result") or ("BUILDING" if building else "UNKNOWN")
                        num = data.get("number", "?")
                        return f"Build #{num}: {result}"
            except Exception:
                pass
            return ""

        def _show_cmd_timer():
            _last_status = ""
            while not _cmd_done.is_set():
                elapsed = _cmd_time.monotonic() - _cmd_start
                if elapsed < 60:
                    t = f"{elapsed:.0f}s"
                else:
                    m, s = divmod(int(elapsed), 60)
                    t = f"{m}m {s:02d}s"

                status_str = ""
                if _is_jenkins and elapsed > 120 and int(elapsed) % 15 == 0:
                    polled = _poll_jenkins_status()
                    if polled:
                        _last_status = polled
                if _last_status:
                    status_str = f" — {_last_status}"

                line = f"\r  {yellow('⏱')} {dim(f'Running... {t}{status_str}')}"
                sys.stdout.write(f"{line}{' ' * 10}")
                sys.stdout.flush()
                _cmd_done.wait(1)
            sys.stdout.write(f"\r{' ' * 80}\r")
            sys.stdout.flush()

        timer_thread = threading.Thread(target=_show_cmd_timer, daemon=True)
        timer_thread.start()

        stdout_data, stderr_data = proc.communicate(timeout=600)
        _cmd_done.set()
        timer_thread.join(timeout=1)

        elapsed = _cmd_time.monotonic() - _cmd_start
        result_stdout = stdout_data.decode("utf-8", errors="replace") if stdout_data else ""
        result_stderr = stderr_data.decode("utf-8", errors="replace") if stderr_data else ""
        raw_output = result_stdout + result_stderr

        display_lines = []
        if result_stdout:
            stdout = result_stdout
            try:
                import json as _json
                parsed = _json.loads(stdout)
                stdout = _json.dumps(parsed, indent=2, ensure_ascii=False)
            except (ValueError, TypeError):
                pass
            display_lines.extend(stdout.splitlines())
        if result_stderr:
            display_lines.extend(result_stderr.splitlines())

        if display_lines:
            for line in display_lines:
                print(_box_line(line))
            if result_stdout:
                try:
                    subprocess.run(
                        ["pbcopy"], input=result_stdout.encode(),
                        capture_output=True, timeout=2,
                    )
                    print(_box_line(dim("(copied to clipboard)")))
                except Exception:
                    pass

        if elapsed < 60:
            time_str = f"{elapsed:.1f}s"
        else:
            m, s = divmod(int(elapsed), 60)
            time_str = f"{m}m {s:02d}s"

        if proc.returncode != 0:
            status_text = f" ✗ Exit code: {proc.returncode} ({time_str})"
            pad = max(0, inner_width - len(status_text))
            print(red(f"  │ {status_text}") + " " * pad + red("│"))
            raw_output += f"\n[exit code: {proc.returncode}]"
        else:
            status_text = f" ✓ Done ({time_str})"
            pad = max(0, inner_width - len(status_text))
            print(red("  │") + green(status_text) + " " * pad + red("│"))

    except subprocess.TimeoutExpired:
        _cmd_done.set()
        timer_thread.join(timeout=1)
        proc.kill()
        stdout_data, stderr_data = proc.communicate()
        raw_output = (stdout_data or b"").decode("utf-8", errors="replace")
        print(_box_line(yellow("Command still running after 10 minutes")))
        print(_box_line(dim("Partial output captured.")))
        if raw_output:
            for line in raw_output.splitlines()[-10:]:
                print(_box_line(line))
    except Exception as e:
        print(_box_line(red(f"Error: {e}")))
        raw_output = f"[error: {e}]"

    print(red(f"  └{'─' * box_width}┘"))
    print()
    return raw_output


# ---------------------------------------------------------------------------
# Offer to run commands
# ---------------------------------------------------------------------------

def _offer_run_commands(
    commands: list[str], cwd: str,
    agent_name: str = "",
) -> list[dict[str, str]]:
    """Offer to run detected shell commands one at a time with Tab selector."""
    results: list[dict[str, str]] = []

    if not commands:
        return results

    for cmd in commands:
        import shutil
        import textwrap
        term_width = shutil.get_terminal_size((80, 24)).columns
        box_width = min(term_width - 4, 100)
        inner = box_width - 2

        trusted = _is_command_trusted(cmd, agent_name, cwd) if agent_name else False

        # Show the command
        print(red(f"  ┌{'─' * box_width}┐"))
        cmd_lines = textwrap.wrap(cmd, width=inner - 3)
        for idx, line in enumerate(cmd_lines):
            if idx == 0:
                prefix = f" {bold('$')} {cyan(line)}"
                vis_len = len(f" $ {line}")
            else:
                prefix = f"   {cyan(line)}"
                vis_len = len(f"   {line}")
            pad = max(0, inner - vis_len)
            print(red(f"  │") + prefix + " " * pad + red("│"))
        print(red(f"  └{'─' * box_width}┘"))

        save_after = False
        if trusted:
            from .rules_loader import PROJECT_RULES_DIRNAME
            rules_path = os.path.join(cwd, PROJECT_RULES_DIRNAME, f"{agent_name}.md") if agent_name else ""
            print(f"  {green('● Auto-approved')} {dim(f'(saved in {rules_path})')}")
        else:
            if agent_name and cwd:
                from .rules_loader import PROJECT_RULES_DIRNAME
                save_path = os.path.join(cwd, PROJECT_RULES_DIRNAME, f"{agent_name}.md")
                save_label = f"Yes & Save to {agent_name} rules"
                choice = _tab_selector("Run this command?", ["Yes", save_label, "No"], default=0)
            else:
                choice = _tab_selector("Run this command?", ["Yes", "No"], default=0)
                choice = 0 if choice == 0 else 2

            if choice == 2:
                print(dim("  Skipped."))
                print()
                continue
            elif choice == 0:
                save_after = False
            elif choice == 1:
                save_after = True

        try:
            resolved = _resolve_placeholders(cmd)
        except (EOFError, KeyboardInterrupt):
            print()
            continue
        if not resolved:
            continue

        try:
            output = _run_single_command(resolved, cwd)
            results.append({"command": resolved, "output": output})
        except (EOFError, KeyboardInterrupt):
            print(dim("\n  Command interrupted."))
            continue
        except Exception as e:
            print(red(f"\n  Command failed: {e}"))
            continue

        if save_after and agent_name and cwd:
            try:
                _save_command_to_rules(resolved, agent_name, cwd)
            except Exception as e:
                print(yellow(f"  ! Could not save to rules: {e}"))

    return results
