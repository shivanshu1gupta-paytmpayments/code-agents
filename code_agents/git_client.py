"""
Git operations client for target repositories.

Wraps git subprocess commands to inspect branches, diffs, logs, and push code.
All operations run asynchronously via asyncio.create_subprocess_exec.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger("code_agents.git_client")

# Only allow safe branch name characters to prevent command injection
_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9._/\-]+$")


class GitOpsError(Exception):
    """Raised when a git operation fails."""

    def __init__(self, message: str, stderr: Optional[str] = None):
        super().__init__(message)
        self.stderr = stderr


def _validate_ref(name: str, label: str = "ref") -> None:
    """Validate a git ref name to prevent command injection."""
    if not name or not _SAFE_REF_RE.match(name):
        raise GitOpsError(f"Invalid {label}: {name!r}")


class GitClient:
    """Async client for git operations on a target repository."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    async def _run(self, *args: str, check: bool = True) -> tuple[str, str]:
        """Run a git command and return (stdout, stderr)."""
        import time as _time
        cmd = ["git", "-C", self.repo_path, *args]
        logger.info("git exec: %s", " ".join(cmd))
        t0 = _time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        elapsed = (_time.monotonic() - t0) * 1000
        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()
        logger.info("git exec done: exit=%d elapsed=%.0fms stdout_len=%d stderr_len=%d",
                     proc.returncode, elapsed, len(stdout_str), len(stderr_str))
        logger.debug("git stdout: %s", stdout_str[:500] if stdout_str else "(empty)")
        if stderr_str:
            logger.debug("git stderr: %s", stderr_str[:500])
        if check and proc.returncode != 0:
            logger.error("git %s FAILED (exit %d): %s", args[0], proc.returncode, stderr_str[:300])
            raise GitOpsError(
                f"git {args[0]} failed (exit {proc.returncode}): {stderr_str}",
                stderr=stderr_str,
            )
        return stdout_str, stderr_str

    async def current_branch(self) -> str:
        """Return the current branch name."""
        stdout, _ = await self._run("rev-parse", "--abbrev-ref", "HEAD")
        return stdout

    async def list_branches(self) -> list[dict[str, str]]:
        """List all local and remote branches."""
        stdout, _ = await self._run(
            "branch", "-a", "--format=%(refname:short) %(objectname:short) %(upstream:short)"
        )
        branches = []
        for line in stdout.splitlines():
            parts = line.split()
            if not parts:
                continue
            entry: dict[str, str] = {"name": parts[0]}
            if len(parts) > 1:
                entry["commit"] = parts[1]
            if len(parts) > 2:
                entry["upstream"] = parts[2]
            branches.append(entry)
        return branches

    async def diff(self, base: str, head: str) -> dict:
        """Show diff between two branches/refs."""
        _validate_ref(base, "base")
        _validate_ref(head, "head")

        # Stat summary
        stat_out, _ = await self._run("diff", "--stat", f"{base}...{head}")

        # Numstat for structured counts
        numstat_out, _ = await self._run("diff", "--numstat", f"{base}...{head}")
        files_changed = 0
        insertions = 0
        deletions = 0
        changed_files = []
        for line in numstat_out.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                files_changed += 1
                ins = int(parts[0]) if parts[0] != "-" else 0
                dels = int(parts[1]) if parts[1] != "-" else 0
                insertions += ins
                deletions += dels
                changed_files.append({
                    "file": parts[2],
                    "insertions": ins,
                    "deletions": dels,
                })

        # Full diff (truncated to avoid huge payloads)
        diff_out, _ = await self._run("diff", f"{base}...{head}")
        max_diff_len = 50000
        truncated = len(diff_out) > max_diff_len
        if truncated:
            diff_out = diff_out[:max_diff_len] + "\n... (truncated)"

        return {
            "base": base,
            "head": head,
            "summary": stat_out,
            "files_changed": files_changed,
            "insertions": insertions,
            "deletions": deletions,
            "changed_files": changed_files,
            "diff": diff_out,
            "truncated": truncated,
        }

    async def log(self, branch: str, limit: int = 20) -> list[dict[str, str]]:
        """Return recent commits on a branch."""
        _validate_ref(branch, "branch")
        stdout, _ = await self._run(
            "log", branch, f"-{limit}",
            "--format=%H|%an|%ai|%s",
        )
        commits = []
        for line in stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3],
                })
        return commits

    async def push(self, branch: str, remote: str = "origin") -> dict:
        """Push a branch to remote. Never force-pushes."""
        _validate_ref(branch, "branch")
        _validate_ref(remote, "remote")
        stdout, stderr = await self._run("push", remote, branch)
        return {
            "success": True,
            "branch": branch,
            "remote": remote,
            "output": stdout or stderr,
        }

    async def fetch(self, remote: str = "origin") -> str:
        """Fetch latest from remote."""
        _validate_ref(remote, "remote")
        stdout, stderr = await self._run("fetch", remote)
        return stdout or stderr or "fetch complete"

    async def status(self) -> dict:
        """Return working tree status summary."""
        stdout, _ = await self._run("status", "--porcelain")
        files = []
        for line in stdout.splitlines():
            if len(line) >= 3:
                files.append({"status": line[:2].strip(), "file": line[3:]})
        return {
            "clean": len(files) == 0,
            "files": files,
        }
