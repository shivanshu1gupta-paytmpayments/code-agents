"""
ArgoCD API: check deployment status, verify pods, fetch logs, and rollback.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..argocd_client import ArgoCDClient, ArgoCDError

logger = logging.getLogger("code_agents.argocd")
router = APIRouter(prefix="/argocd", tags=["argocd"])


def _get_client() -> ArgoCDClient:
    """Build ArgoCDClient from environment variables."""
    base_url = os.getenv("ARGOCD_URL")
    if not base_url:
        raise HTTPException(
            status_code=503,
            detail="ARGOCD_URL is not set. Configure ArgoCD connection in environment.",
        )
    auth_token = os.getenv("ARGOCD_AUTH_TOKEN")
    if not auth_token:
        raise HTTPException(
            status_code=503,
            detail="ARGOCD_AUTH_TOKEN is not set.",
        )
    verify_ssl = os.getenv("ARGOCD_VERIFY_SSL", "1").strip().lower() not in ("0", "false", "no")
    return ArgoCDClient(
        base_url=base_url,
        auth_token=auth_token,
        verify_ssl=verify_ssl,
    )


class SyncRequest(BaseModel):
    """Request to sync an ArgoCD application."""
    revision: Optional[str] = Field(None, description="Target revision (default: latest)")


class RollbackRequest(BaseModel):
    """Request to rollback an ArgoCD application."""
    revision: Union[int, str] = Field(
        ...,
        description="Deployment history revision ID (int) or 'previous' for the last revision",
    )


@router.get("/apps/{app_name}/status")
async def get_app_status(app_name: str):
    """Get ArgoCD application sync and health status."""
    try:
        client = _get_client()
        result = await client.get_app_status(app_name)
        logger.info("app_status %s: sync=%s health=%s",
                     app_name, result["sync_status"], result["health_status"])
        return result
    except ArgoCDError as e:
        logger.error("get_app_status failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/pods")
async def list_pods(app_name: str):
    """List pods for an ArgoCD application with image tags and health."""
    try:
        client = _get_client()
        pods = await client.list_pods(app_name)
        return {"app_name": app_name, "pods": pods, "count": len(pods)}
    except ArgoCDError as e:
        logger.error("list_pods failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/pods/{pod_name}/logs")
async def get_pod_logs(
    app_name: str,
    pod_name: str,
    namespace: str = "default",
    container: Optional[str] = None,
    tail: int = 200,
):
    """Fetch pod logs and scan for error patterns (ERROR, FATAL, Exception, panic)."""
    try:
        client = _get_client()
        result = await client.get_pod_logs(
            app_name=app_name,
            pod_name=pod_name,
            namespace=namespace,
            container=container,
            tail_lines=tail,
        )
        if result["has_errors"]:
            logger.warning("Pod %s has %d error lines", pod_name, len(result["error_lines"]))
        return result
    except ArgoCDError as e:
        logger.error("get_pod_logs failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/apps/{app_name}/sync")
async def sync_app(app_name: str, req: Optional[SyncRequest] = None):
    """Trigger an ArgoCD application sync."""
    try:
        client = _get_client()
        result = await client.sync_app(
            app_name=app_name,
            revision=req.revision if req else None,
        )
        logger.info("sync_app %s: triggered", app_name)
        return result
    except ArgoCDError as e:
        logger.error("sync_app failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/apps/{app_name}/rollback")
async def rollback_app(app_name: str, req: RollbackRequest):
    """
    Rollback an ArgoCD application to a previous deployment revision.

    Pass revision as an integer (history ID) or "previous" to rollback to the last deployment.
    """
    try:
        client = _get_client()

        # Resolve "previous" to actual revision ID
        revision_id: int
        if isinstance(req.revision, str) and req.revision.lower() == "previous":
            history = await client.get_history(app_name)
            if len(history) < 2:
                raise HTTPException(
                    status_code=422,
                    detail="No previous revision available in deployment history.",
                )
            revision_id = history[-2]["id"]  # Second-to-last is the previous deployment
        else:
            revision_id = int(req.revision)

        result = await client.rollback(app_name=app_name, revision_id=revision_id)
        logger.info("rollback %s to revision %d", app_name, revision_id)
        return result
    except ArgoCDError as e:
        logger.error("rollback failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/apps/{app_name}/history")
async def get_history(app_name: str):
    """Get deployment history for an ArgoCD application."""
    try:
        client = _get_client()
        history = await client.get_history(app_name)
        return {"app_name": app_name, "history": history, "count": len(history)}
    except ArgoCDError as e:
        logger.error("get_history failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/apps/{app_name}/wait-sync")
async def wait_for_sync(app_name: str):
    """Wait until application is synced and healthy (long-poll)."""
    try:
        client = _get_client()
        result = await client.wait_for_sync(app_name)
        return result
    except ArgoCDError as e:
        logger.error("wait_for_sync failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
