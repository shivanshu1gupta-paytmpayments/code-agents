"""
Jenkins REST API client for triggering and monitoring build/deploy jobs.

Uses httpx for async HTTP. Authenticates via HTTP Basic (username + API token).
Handles CSRF crumb for Jenkins instances that require it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger("code_agents.jenkins_client")


class JenkinsError(Exception):
    """Raised when a Jenkins API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class JenkinsClient:
    """Async client for the Jenkins REST API."""

    def __init__(
        self,
        base_url: str,
        username: str,
        api_token: str,
        timeout: float = 30.0,
        poll_interval: float = 5.0,
        poll_timeout: float = 600.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, api_token)
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self._crumb: Optional[dict[str, str]] = None

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            auth=self.auth,
            timeout=self.timeout,
            follow_redirects=True,
        )

    async def _get_crumb(self, client: httpx.AsyncClient) -> dict[str, str]:
        """Fetch CSRF crumb if Jenkins requires it. Cached per instance."""
        if self._crumb is not None:
            return self._crumb
        try:
            r = await client.get("/crumbIssuer/api/json")
            if r.status_code == 200:
                data = r.json()
                self._crumb = {data["crumbRequestField"]: data["crumb"]}
                return self._crumb
        except Exception:
            pass
        self._crumb = {}
        return self._crumb

    async def trigger_build(
        self,
        job_name: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> dict:
        """
        Trigger a Jenkins build job.

        Returns dict with queue_id for tracking.
        """
        async with self._client() as client:
            crumb = await self._get_crumb(client)
            headers = dict(crumb) if crumb else {}

            # URL-encode job name for folder paths (e.g., "folder/job")
            job_path = "/job/" + "/job/".join(job_name.split("/"))

            if parameters:
                url = f"{job_path}/buildWithParameters"
                logger.info("jenkins trigger_build: POST %s params=%s", url, list(parameters.keys()))
                r = await client.post(url, data=parameters, headers=headers)
            else:
                url = f"{job_path}/build"
                logger.info("jenkins trigger_build: POST %s (no params)", url)
                r = await client.post(url, headers=headers)

            logger.info("jenkins trigger_build response: status=%d location=%s", r.status_code, r.headers.get("Location", "-"))
            if r.status_code not in (200, 201, 302):
                raise JenkinsError(
                    f"Failed to trigger build: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )

            # Extract queue ID from Location header
            location = r.headers.get("Location", "")
            queue_id = None
            if "/queue/item/" in location:
                try:
                    queue_id = int(location.rstrip("/").split("/")[-1])
                except ValueError:
                    pass

            logger.info("Triggered build for %s, queue_id=%s", job_name, queue_id)
            return {
                "job_name": job_name,
                "queue_id": queue_id,
                "status": "queued",
            }

    async def get_build_from_queue(self, queue_id: int) -> Optional[int]:
        """Poll queue item until it gets a build number. Returns build number or None."""
        async with self._client() as client:
            deadline = time.monotonic() + self.poll_timeout
            while time.monotonic() < deadline:
                r = await client.get(f"/queue/item/{queue_id}/api/json")
                if r.status_code != 200:
                    raise JenkinsError(
                        f"Failed to get queue item: HTTP {r.status_code}",
                        status_code=r.status_code,
                    )
                data = r.json()
                executable = data.get("executable")
                if executable and executable.get("number"):
                    return executable["number"]
                if data.get("cancelled"):
                    return None
                await asyncio.sleep(self.poll_interval)
            raise JenkinsError(f"Queue item {queue_id} did not start within {self.poll_timeout}s")

    async def get_build_status(self, job_name: str, build_number: int) -> dict:
        """Get build status and details."""
        job_path = "/job/" + "/job/".join(job_name.split("/"))
        async with self._client() as client:
            r = await client.get(f"{job_path}/{build_number}/api/json")
            if r.status_code != 200:
                raise JenkinsError(
                    f"Failed to get build status: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            data = r.json()
            return {
                "job_name": job_name,
                "number": data.get("number"),
                "result": data.get("result"),  # SUCCESS, FAILURE, UNSTABLE, ABORTED, None (building)
                "building": data.get("building", False),
                "duration": data.get("duration", 0),
                "estimated_duration": data.get("estimatedDuration", 0),
                "timestamp": data.get("timestamp"),
                "url": data.get("url"),
                "display_name": data.get("displayName"),
            }

    async def get_build_log(self, job_name: str, build_number: int) -> str:
        """Get console output for a build."""
        job_path = "/job/" + "/job/".join(job_name.split("/"))
        async with self._client() as client:
            r = await client.get(f"{job_path}/{build_number}/consoleText")
            if r.status_code != 200:
                raise JenkinsError(
                    f"Failed to get build log: HTTP {r.status_code}",
                    status_code=r.status_code,
                )
            text = r.text
            # Truncate very long logs
            max_len = 50000
            if len(text) > max_len:
                text = text[-max_len:]
                text = "... (truncated, showing last 50KB)\n" + text
            return text

    async def get_last_build(self, job_name: str) -> dict:
        """Get info about the last build of a job."""
        job_path = "/job/" + "/job/".join(job_name.split("/"))
        async with self._client() as client:
            r = await client.get(f"{job_path}/lastBuild/api/json")
            if r.status_code != 200:
                raise JenkinsError(
                    f"Failed to get last build: HTTP {r.status_code}",
                    status_code=r.status_code,
                    response_text=r.text[:500],
                )
            data = r.json()
            return {
                "job_name": job_name,
                "number": data.get("number"),
                "result": data.get("result"),
                "building": data.get("building", False),
                "url": data.get("url"),
            }

    async def wait_for_build(self, job_name: str, build_number: int) -> dict:
        """Poll build status until it finishes. Returns final status."""
        logger.info("jenkins wait_for_build: %s #%d (poll_interval=%.0fs timeout=%.0fs)",
                     job_name, build_number, self.poll_interval, self.poll_timeout)
        deadline = time.monotonic() + self.poll_timeout
        poll_count = 0
        while time.monotonic() < deadline:
            poll_count += 1
            status = await self.get_build_status(job_name, build_number)
            if not status["building"]:
                logger.info(
                    "jenkins build %s #%d finished: result=%s duration=%dms polls=%d",
                    job_name, build_number, status["result"], status.get("duration", 0), poll_count,
                )
                return status
            logger.debug("jenkins build %s #%d still building (poll %d)", job_name, build_number, poll_count)
            await asyncio.sleep(self.poll_interval)
        logger.error("jenkins build %s #%d TIMEOUT after %.0fs (%d polls)",
                      job_name, build_number, self.poll_timeout, poll_count)
        raise JenkinsError(
            f"Build {job_name} #{build_number} did not complete within {self.poll_timeout}s"
        )
