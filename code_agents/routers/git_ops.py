"""
Git operations API: inspect branches, diffs, logs, and push code on a target repository.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..git_client import GitClient, GitOpsError

logger = logging.getLogger("code_agents.git_ops")
router = APIRouter(prefix="/git", tags=["git"])


def _resolve_repo_path(repo_path: Optional[str] = None) -> str:
    """Resolve repo path: request param → env var → cwd."""
    path = repo_path or os.getenv("TARGET_REPO_PATH") or os.getcwd()
    if not os.path.isdir(path):
        raise HTTPException(status_code=422, detail=f"Repository path does not exist: {path}")
    return path


def _get_client(repo_path: Optional[str] = None) -> GitClient:
    """Build GitClient from request param, env var, or cwd."""
    return GitClient(repo_path=_resolve_repo_path(repo_path))


class PushRequest(BaseModel):
    """Request to push a branch to remote."""
    branch: str = Field(..., description="Branch name to push")
    remote: str = Field("origin", description="Remote name (default: origin)")
    repo_path: Optional[str] = Field(None, description="Override target repo path")


class DiffQuery(BaseModel):
    """Query parameters for diff endpoint."""
    base: str = Field("main", description="Base branch/ref")
    head: str = Field(..., description="Head branch/ref to compare")


@router.get("/branches")
async def list_branches(repo_path: Optional[str] = None):
    """List all local and remote branches in the target repository."""
    try:
        client = _get_client(repo_path)
        return {"branches": await client.list_branches(), "repo_path": client.repo_path}
    except GitOpsError as e:
        logger.error("list_branches failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/current-branch")
async def current_branch(repo_path: Optional[str] = None):
    """Get the current branch of the target repository."""
    try:
        client = _get_client(repo_path)
        branch = await client.current_branch()
        return {"branch": branch, "repo_path": client.repo_path}
    except GitOpsError as e:
        logger.error("current_branch failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/diff")
async def get_diff(base: str = "main", head: str = "HEAD", repo_path: Optional[str] = None):
    """Show diff between two branches/refs in the target repository."""
    try:
        client = _get_client(repo_path)
        result = await client.diff(base=base, head=head)
        result["repo_path"] = client.repo_path
        logger.info("diff %s...%s: %d files, +%d/-%d", base, head,
                     result["files_changed"], result["insertions"], result["deletions"])
        return result
    except GitOpsError as e:
        logger.error("diff failed: %s", e)
        raise HTTPException(status_code=422 if "Invalid" in str(e) else 502, detail=str(e))


@router.get("/log")
async def get_log(branch: str = "HEAD", limit: int = 20, repo_path: Optional[str] = None):
    """Show commit log for a branch in the target repository."""
    try:
        client = _get_client(repo_path)
        commits = await client.log(branch=branch, limit=min(limit, 100))
        return {"branch": branch, "commits": commits, "count": len(commits), "repo_path": client.repo_path}
    except GitOpsError as e:
        logger.error("log failed: %s", e)
        raise HTTPException(status_code=422 if "Invalid" in str(e) else 502, detail=str(e))


@router.post("/push")
async def push_branch(req: PushRequest):
    """Push a branch to remote. Never force-pushes."""
    try:
        client = _get_client(req.repo_path)
        result = await client.push(branch=req.branch, remote=req.remote)
        result["repo_path"] = client.repo_path
        logger.info("push %s to %s: success", req.branch, req.remote)
        return result
    except GitOpsError as e:
        logger.error("push failed: %s", e)
        raise HTTPException(status_code=422 if "Invalid" in str(e) else 502, detail=str(e))


@router.get("/status")
async def get_status(repo_path: Optional[str] = None):
    """Get working tree status of the target repository."""
    try:
        client = _get_client(repo_path)
        result = await client.status()
        result["repo_path"] = client.repo_path
        return result
    except GitOpsError as e:
        logger.error("status failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/fetch")
async def fetch_remote(remote: str = "origin", repo_path: Optional[str] = None):
    """Fetch latest from remote."""
    try:
        client = _get_client(repo_path)
        output = await client.fetch(remote=remote)
        return {"remote": remote, "output": output, "repo_path": client.repo_path}
    except GitOpsError as e:
        logger.error("fetch failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
