"""
ArgoCD REST API client for deployment verification and rollback.

Uses httpx for async HTTP. Authenticates via Bearer token.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger("code_agents.argocd_client")


class ArgoCDError(Exception):
    """Raised when an ArgoCD API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class ArgoCDClient:
    """Async client for the ArgoCD REST API."""

    def __init__(
        self,
        base_url: str,
        auth_token: str,
        verify_ssl: bool = True,
        timeout: float = 30.0,
        poll_interval: float = 5.0,
        poll_timeout: float = 300.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.auth_token}"},
            verify=self.verify_ssl,
            timeout=self.timeout,
            follow_redirects=True,
        )

    async def get_app_status(self, app_name: str) -> dict:
        """Get application sync and health status."""
        async with self._client() as client:
            r = await client.get(f"/api/v1/applications/{app_name}")
            if r.status_code != 200:
                raise ArgoCDError(
                    f"Failed to get app status: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            data = r.json()
            status = data.get("status", {})
            sync = status.get("sync", {})
            health = status.get("health", {})

            # Extract images from summary
            images = []
            summary = status.get("summary", {})
            if summary.get("images"):
                images = summary["images"]

            return {
                "app_name": app_name,
                "sync_status": sync.get("status", "Unknown"),
                "health_status": health.get("status", "Unknown"),
                "revision": sync.get("revision", ""),
                "images": images,
                "conditions": status.get("conditions", []),
                "source": data.get("spec", {}).get("source", {}),
            }

    async def list_pods(self, app_name: str) -> list[dict]:
        """List pods for an application from the resource tree."""
        async with self._client() as client:
            r = await client.get(f"/api/v1/applications/{app_name}/resource-tree")
            if r.status_code != 200:
                raise ArgoCDError(
                    f"Failed to get resource tree: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            data = r.json()
            pods = []
            for node in data.get("nodes", []):
                if node.get("kind") == "Pod":
                    health = node.get("health", {})
                    pods.append({
                        "name": node.get("name", ""),
                        "namespace": node.get("namespace", ""),
                        "status": health.get("status", "Unknown"),
                        "message": health.get("message", ""),
                        "images": node.get("images", []),
                        "ready": health.get("status") == "Healthy",
                    })
            return pods

    async def get_pod_logs(
        self,
        app_name: str,
        pod_name: str,
        namespace: str,
        container: Optional[str] = None,
        tail_lines: int = 200,
    ) -> dict:
        """Fetch pod logs via ArgoCD API."""
        async with self._client() as client:
            params: dict[str, Any] = {
                "podName": pod_name,
                "namespace": namespace,
                "tailLines": tail_lines,
            }
            if container:
                params["container"] = container

            r = await client.get(
                f"/api/v1/applications/{app_name}/logs",
                params=params,
            )
            if r.status_code != 200:
                raise ArgoCDError(
                    f"Failed to get pod logs: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )

            logs = r.text

            # Scan for error patterns
            error_patterns = re.compile(
                r"(ERROR|FATAL|Exception|Traceback|panic:|CRITICAL)",
                re.IGNORECASE,
            )
            error_lines = [
                line for line in logs.splitlines()
                if error_patterns.search(line)
            ]

            return {
                "pod_name": pod_name,
                "namespace": namespace,
                "logs": logs,
                "error_lines": error_lines[:50],  # Limit
                "has_errors": len(error_lines) > 0,
                "total_lines": len(logs.splitlines()),
            }

    async def sync_app(self, app_name: str, revision: Optional[str] = None) -> dict:
        """Trigger an application sync."""
        async with self._client() as client:
            body: dict[str, Any] = {}
            if revision:
                body["revision"] = revision

            r = await client.post(
                f"/api/v1/applications/{app_name}/sync",
                json=body,
            )
            if r.status_code != 200:
                raise ArgoCDError(
                    f"Failed to sync app: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            return {"app_name": app_name, "status": "sync_triggered", "revision": revision}

    async def rollback(self, app_name: str, revision_id: int) -> dict:
        """Rollback application to a previous deployment revision."""
        async with self._client() as client:
            body = {"id": revision_id}
            r = await client.put(
                f"/api/v1/applications/{app_name}/rollback",
                json=body,
            )
            if r.status_code != 200:
                raise ArgoCDError(
                    f"Failed to rollback: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            return {
                "app_name": app_name,
                "status": "rollback_triggered",
                "target_revision_id": revision_id,
            }

    async def get_history(self, app_name: str) -> list[dict]:
        """Get deployment history for an application."""
        async with self._client() as client:
            r = await client.get(f"/api/v1/applications/{app_name}")
            if r.status_code != 200:
                raise ArgoCDError(
                    f"Failed to get app: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            data = r.json()
            history = data.get("status", {}).get("history", [])
            return [
                {
                    "id": entry.get("id"),
                    "revision": entry.get("revision", ""),
                    "deployed_at": entry.get("deployedAt", ""),
                    "source": entry.get("source", {}),
                }
                for entry in history
            ]

    async def wait_for_sync(self, app_name: str) -> dict:
        """Poll until app is synced and healthy."""
        logger.info("argocd wait_for_sync: app=%s (poll_interval=%.0fs timeout=%.0fs)",
                     app_name, self.poll_interval, self.poll_timeout)
        deadline = time.monotonic() + self.poll_timeout
        poll_count = 0
        while time.monotonic() < deadline:
            poll_count += 1
            status = await self.get_app_status(app_name)
            if (
                status["sync_status"] == "Synced"
                and status["health_status"] == "Healthy"
            ):
                logger.info("argocd app %s is synced and healthy after %d polls", app_name, poll_count)
                return status
            logger.info(
                "argocd waiting for %s: sync=%s health=%s (poll %d)",
                app_name, status["sync_status"], status["health_status"], poll_count,
            )
            await asyncio.sleep(self.poll_interval)
        logger.error("argocd app %s TIMEOUT after %.0fs (%d polls)", app_name, self.poll_timeout, poll_count)
        raise ArgoCDError(
            f"App {app_name} did not reach Synced/Healthy within {self.poll_timeout}s"
        )
