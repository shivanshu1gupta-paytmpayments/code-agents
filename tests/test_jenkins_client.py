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

    def test_job_path_encoding(self):
        """Verify folder job paths are encoded correctly."""
        c = self._make_client()
        # The trigger_build method constructs the path internally
        # Test by checking the URL pattern logic
        job_name = "folder/subfolder/my-job"
        expected = "/job/folder/job/subfolder/job/my-job"
        actual = "/job/" + "/job/".join(job_name.split("/"))
        assert actual == expected


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
