"""Tests for jenkins_client.py — unit tests with mocked HTTP."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.jenkins_client import JenkinsClient, JenkinsError


class TestJenkinsClient:
    def _make_client(self):
        return JenkinsClient(
            base_url="https://jenkins.example.com",
            username="testuser",
            api_token="testtoken",
            poll_interval=0.1,
            poll_timeout=1.0,
        )

    def test_init(self):
        c = self._make_client()
        assert c.base_url == "https://jenkins.example.com"
        assert c.auth == ("testuser", "testtoken")

    def test_init_strips_trailing_slash(self):
        c = JenkinsClient(
            base_url="https://jenkins.example.com/",
            username="u", api_token="t",
        )
        assert c.base_url == "https://jenkins.example.com"

    def test_job_path_simple(self):
        """Simple job name."""
        c = self._make_client()
        assert c._job_path("my-job") == "/job/my-job"

    def test_job_path_folder(self):
        """Two-level folder job."""
        c = self._make_client()
        assert c._job_path("pg2/my-job") == "/job/pg2/job/my-job"

    def test_job_path_deep_folder(self):
        """Three-level folder job (like pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz)."""
        c = self._make_client()
        assert c._job_path("pg2/pg2-dev-build-jobs/pg2-dev-pg-acquiring-biz") == \
            "/job/pg2/job/pg2-dev-build-jobs/job/pg2-dev-pg-acquiring-biz"

    def test_job_path_strips_job_prefix(self):
        """Handles misconfigured input with 'job/' prefixes (copy-pasted from Jenkins URL)."""
        c = self._make_client()
        assert c._job_path("job/pg2/job/pg2-dev-build-jobs/") == \
            "/job/pg2/job/pg2-dev-build-jobs"

    def test_job_path_strips_trailing_slash(self):
        """Trailing slashes are stripped."""
        c = self._make_client()
        assert c._job_path("pg2/pg2-dev-build-jobs/") == \
            "/job/pg2/job/pg2-dev-build-jobs"


class TestExtractBuildVersion:
    """Test build version extraction from console logs."""

    def test_docker_tag(self):
        log = "Building image...\nPushing repo/my-service:1.2.3-42\nDone."
        assert JenkinsClient.extract_build_version(log) == "1.2.3-42"

    def test_build_version_env(self):
        log = "Compiling...\nBUILD_VERSION=2.5.0-SNAPSHOT\nUpload complete."
        assert JenkinsClient.extract_build_version(log) == "2.5.0-SNAPSHOT"

    def test_version_equals(self):
        log = "Setting version=3.1.0\nBuild success."
        assert JenkinsClient.extract_build_version(log) == "3.1.0"

    def test_build_tag_number(self):
        log = "Starting...\nbuild tag: 157\nFinished: SUCCESS"
        assert JenkinsClient.extract_build_version(log) == "157"

    def test_build_hash_number(self):
        log = "Build #42 completed\nFinished: SUCCESS"
        assert JenkinsClient.extract_build_version(log) == "42"

    def test_artifact_upload(self):
        log = "Uploading my-service-1.5.2.jar to nexus\nDone."
        assert JenkinsClient.extract_build_version(log) == "1.5.2"

    def test_docker_v_prefix(self):
        log = "Successfully built image:v2.0.1\nPush complete."
        assert JenkinsClient.extract_build_version(log) == "v2.0.1"

    def test_no_version_found(self):
        log = "Compiling...\nAll tests passed.\nFinished: SUCCESS"
        assert JenkinsClient.extract_build_version(log) is None

    def test_empty_log(self):
        assert JenkinsClient.extract_build_version("") is None

    def test_last_match_wins(self):
        """Multiple versions — last one (final artifact) should be returned."""
        log = "version=1.0.0\nRebuilding...\nversion=2.0.0\nDone."
        assert JenkinsClient.extract_build_version(log) == "2.0.0"

    def test_version_in_last_200_lines(self):
        """Only scans last 200 lines."""
        early = "BUILD_VERSION=1.0.0\n" + ("noise\n" * 300)
        late = "BUILD_VERSION=2.0.0\nDone."
        assert JenkinsClient.extract_build_version(early + late) == "2.0.0"


class TestArgoCDClient:
    """Tests for argocd_client.py — unit tests."""

    def test_init(self):
        from code_agents.argocd_client import ArgoCDClient
        c = ArgoCDClient(
            base_url="https://argocd.example.com/",
            auth_token="test-token",
            verify_ssl=False,
        )
        assert c.base_url == "https://argocd.example.com"
        assert c.auth_token == "test-token"
        assert c.verify_ssl is False

    def test_init_defaults(self):
        from code_agents.argocd_client import ArgoCDClient
        c = ArgoCDClient(
            base_url="https://argocd.example.com",
            auth_token="token",
        )
        assert c.verify_ssl is True
        assert c.timeout == 30.0
        assert c.poll_timeout == 300.0
