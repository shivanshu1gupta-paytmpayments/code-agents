"""
Jenkins CI/CD API: trigger builds, monitor status, and fetch logs.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..jenkins_client import JenkinsClient, JenkinsError

logger = logging.getLogger("code_agents.jenkins")
router = APIRouter(prefix="/jenkins", tags=["jenkins"])


def _get_client() -> JenkinsClient:
    """Build JenkinsClient from environment variables."""
    base_url = os.getenv("JENKINS_URL")
    if not base_url:
        raise HTTPException(
            status_code=503,
            detail="JENKINS_URL is not set. Configure Jenkins connection in environment.",
        )
    username = os.getenv("JENKINS_USERNAME")
    api_token = os.getenv("JENKINS_API_TOKEN")
    if not username or not api_token:
        raise HTTPException(
            status_code=503,
            detail="JENKINS_USERNAME and JENKINS_API_TOKEN must both be set.",
        )
    return JenkinsClient(
        base_url=base_url,
        username=username,
        api_token=api_token,
    )


class TriggerBuildRequest(BaseModel):
    """Request to trigger a Jenkins build."""
    job_name: str = Field(..., description="Jenkins job name (e.g., 'pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz')")
    branch: Optional[str] = Field(None, description="Branch name — convenience field, added to parameters as 'branch'")
    parameters: Optional[dict[str, Any]] = Field(None, description="Build parameters — use exact names from /jenkins/jobs/{path}/parameters")


class WaitForBuildRequest(BaseModel):
    """Request to wait for a build to complete."""
    timeout: Optional[float] = Field(None, description="Max seconds to wait (default: 600)")


@router.get("/jobs")
async def list_jobs(folder: Optional[str] = None):
    """
    List jobs in a Jenkins folder (or root if no folder specified).

    Query params:
      ?folder=pg2/pg2-dev-build-jobs   — list jobs in this folder

    Returns list of jobs with name, type (folder/job), color, and URL.
    Use this to discover available build/deploy jobs.
    """
    try:
        client = _get_client()
        jobs = await client.list_jobs(folder)
        return {
            "folder": folder or "(root)",
            "count": len(jobs),
            "jobs": jobs,
        }
    except JenkinsError as e:
        logger.error("list_jobs failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/jobs/{job_path:path}/parameters")
async def get_job_parameters(job_path: str):
    """
    Get the parameter definitions for a parameterized Jenkins job.

    Path: /jenkins/jobs/pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz/parameters

    Returns parameter names, types, defaults, descriptions, and choices.
    Use this to know what parameters to pass when triggering a build.
    """
    try:
        client = _get_client()
        params = await client.get_job_parameters(job_path)
        return {
            "job_name": job_path,
            "parameters": params,
        }
    except JenkinsError as e:
        logger.error("get_job_parameters failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/build")
async def trigger_build(req: TriggerBuildRequest):
    """
    Trigger a Jenkins build job.

    Returns queue_id for tracking. If branch is specified, it's added as 'branch' parameter.
    """
    try:
        client = _get_client()
        params = dict(req.parameters or {})
        if req.branch and "branch" not in params:
            params["branch"] = req.branch
        result = await client.trigger_build(
            job_name=req.job_name,
            parameters=params if params else None,
        )

        # Try to resolve build number from queue
        if result.get("queue_id"):
            try:
                build_number = await client.get_build_from_queue(result["queue_id"])
                if build_number:
                    result["build_number"] = build_number
                    result["status"] = "started"
            except JenkinsError:
                pass  # Queue lookup failed, client can retry

        logger.info("trigger_build: job=%s queue=%s build=%s",
                     req.job_name, result.get("queue_id"), result.get("build_number"))
        return result
    except JenkinsError as e:
        logger.error("trigger_build failed: %s", e)
        raise HTTPException(
            status_code=422 if e.status_code in (400, 403, 404) else 502,
            detail=str(e),
        )


@router.post("/build-and-wait")
async def trigger_build_and_wait(req: TriggerBuildRequest):
    """
    Trigger a build, poll until complete, and extract build version from logs.

    This is the all-in-one endpoint: trigger → poll → extract version.
    Returns: job_name, build_number, result (SUCCESS/FAILURE), build_version,
    duration, log_tail (last 30 lines of console).

    The build_version can be passed directly to the deploy job.
    """
    try:
        client = _get_client()
        # Increase timeout for long builds
        client.poll_timeout = 1200.0  # 20 minutes

        params = dict(req.parameters or {})
        if req.branch and "branch" not in params:
            params["branch"] = req.branch

        result = await client.trigger_and_wait(
            job_name=req.job_name,
            parameters=params if params else None,
        )

        logger.info(
            "build_and_wait: job=%s build=#%s result=%s version=%s",
            req.job_name, result.get("number"), result.get("result"), result.get("build_version"),
        )
        return result
    except JenkinsError as e:
        logger.error("build_and_wait failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/build/{job_name:path}/{build_number}/status")
async def get_build_status(job_name: str, build_number: int):
    """Get the status of a specific build."""
    try:
        client = _get_client()
        return await client.get_build_status(job_name, build_number)
    except JenkinsError as e:
        logger.error("get_build_status failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/build/{job_name:path}/{build_number}/log")
async def get_build_log(job_name: str, build_number: int):
    """Get console output for a build."""
    try:
        client = _get_client()
        log_text = await client.get_build_log(job_name, build_number)
        return {"job_name": job_name, "build_number": build_number, "log": log_text}
    except JenkinsError as e:
        logger.error("get_build_log failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/build/{job_name:path}/last")
async def get_last_build(job_name: str):
    """Get info about the latest build of a job."""
    try:
        client = _get_client()
        return await client.get_last_build(job_name)
    except JenkinsError as e:
        logger.error("get_last_build failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/build/{job_name:path}/{build_number}/wait")
async def wait_for_build(job_name: str, build_number: int, req: Optional[WaitForBuildRequest] = None):
    """
    Long-poll until a build completes.

    Returns the final build status (SUCCESS, FAILURE, UNSTABLE, ABORTED).
    """
    try:
        client = _get_client()
        if req and req.timeout:
            client.poll_timeout = req.timeout
        result = await client.wait_for_build(job_name, build_number)
        return result
    except JenkinsError as e:
        logger.error("wait_for_build failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
