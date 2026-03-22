"""Tests for env_loader.py — centralized .env configuration."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.env_loader import (
    GLOBAL_VARS,
    REPO_VARS,
    RUNTIME_VARS,
    PER_REPO_FILENAME,
    load_all_env,
    split_vars,
)


class TestSplitVars:
    """Test variable classification into global vs per-repo."""

    def test_api_keys_are_global(self):
        g, r = split_vars({
            "CURSOR_API_KEY": "sk-123",
            "ANTHROPIC_API_KEY": "sk-456",
        })
        assert "CURSOR_API_KEY" in g
        assert "ANTHROPIC_API_KEY" in g
        assert r == {}

    def test_jenkins_is_per_repo(self):
        g, r = split_vars({
            "JENKINS_URL": "http://jenkins",
            "JENKINS_USERNAME": "admin",
            "JENKINS_API_TOKEN": "tok",
        })
        assert g == {}
        assert "JENKINS_URL" in r
        assert "JENKINS_USERNAME" in r
        assert "JENKINS_API_TOKEN" in r

    def test_argocd_is_per_repo(self):
        g, r = split_vars({
            "ARGOCD_URL": "http://argocd",
            "ARGOCD_AUTH_TOKEN": "tok",
            "ARGOCD_APP_NAME": "myapp",
        })
        assert g == {}
        assert len(r) == 3

    def test_target_repo_path_never_stored(self):
        g, r = split_vars({
            "TARGET_REPO_PATH": "/some/path",
            "CURSOR_API_KEY": "sk-123",
        })
        assert "TARGET_REPO_PATH" not in g
        assert "TARGET_REPO_PATH" not in r
        assert "CURSOR_API_KEY" in g

    def test_mixed_vars_split_correctly(self):
        g, r = split_vars({
            "CURSOR_API_KEY": "sk-123",
            "HOST": "0.0.0.0",
            "JENKINS_URL": "http://jenkins",
            "ARGOCD_URL": "http://argocd",
            "TARGET_REPO_PATH": "/path",
            "REDASH_BASE_URL": "http://redash",
            "TARGET_TEST_COMMAND": "pytest",
        })
        assert "CURSOR_API_KEY" in g
        assert "HOST" in g
        assert "REDASH_BASE_URL" in g
        assert "JENKINS_URL" in r
        assert "ARGOCD_URL" in r
        assert "TARGET_TEST_COMMAND" in r
        assert "TARGET_REPO_PATH" not in g
        assert "TARGET_REPO_PATH" not in r

    def test_empty_input(self):
        g, r = split_vars({})
        assert g == {}
        assert r == {}

    def test_unknown_vars_default_to_global(self):
        g, r = split_vars({"MY_CUSTOM_VAR": "value"})
        assert "MY_CUSTOM_VAR" in g
        assert r == {}

    def test_server_vars_are_global(self):
        g, r = split_vars({"HOST": "0.0.0.0", "PORT": "8000", "LOG_LEVEL": "DEBUG"})
        assert len(g) == 3
        assert r == {}

    def test_redash_vars_are_global(self):
        g, r = split_vars({
            "REDASH_BASE_URL": "http://redash",
            "REDASH_USERNAME": "user",
            "REDASH_PASSWORD": "pass",
        })
        assert len(g) == 3
        assert r == {}

    def test_testing_vars_are_per_repo(self):
        g, r = split_vars({
            "TARGET_TEST_COMMAND": "pytest --cov",
            "TARGET_COVERAGE_THRESHOLD": "80",
            "TARGET_REPO_REMOTE": "origin",
        })
        assert g == {}
        assert len(r) == 3


class TestLoadAllEnv:
    """Test the centralized env loading order."""

    def test_sets_target_repo_path_from_cwd(self, tmp_path, monkeypatch):
        """TARGET_REPO_PATH is always set to cwd."""
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)
        load_all_env(str(tmp_path))
        assert os.environ["TARGET_REPO_PATH"] == str(tmp_path)

    def test_loads_global_config(self, tmp_path, monkeypatch):
        """Global config is loaded first."""
        global_dir = tmp_path / "home" / ".code-agents"
        global_dir.mkdir(parents=True)
        global_env = global_dir / "config.env"
        global_env.write_text("CURSOR_API_KEY=global-key\n")

        monkeypatch.delenv("CURSOR_API_KEY", raising=False)
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)

        with patch("code_agents.env_loader.GLOBAL_ENV_PATH", global_env):
            load_all_env(str(tmp_path))

        assert os.environ.get("CURSOR_API_KEY") == "global-key"

    def test_legacy_env_overrides_global(self, tmp_path, monkeypatch):
        """Legacy .env overrides global config."""
        global_dir = tmp_path / "home" / ".code-agents"
        global_dir.mkdir(parents=True)
        global_env = global_dir / "config.env"
        global_env.write_text("CURSOR_API_KEY=global-key\n")

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env").write_text("CURSOR_API_KEY=legacy-key\n")

        monkeypatch.delenv("CURSOR_API_KEY", raising=False)
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)

        with patch("code_agents.env_loader.GLOBAL_ENV_PATH", global_env):
            load_all_env(str(repo))

        assert os.environ.get("CURSOR_API_KEY") == "legacy-key"

    def test_per_repo_overrides_legacy(self, tmp_path, monkeypatch):
        """Per-repo .env.code-agents overrides legacy .env."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env").write_text("JENKINS_URL=legacy-url\n")
        (repo / PER_REPO_FILENAME).write_text("JENKINS_URL=repo-url\n")

        monkeypatch.delenv("JENKINS_URL", raising=False)
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)

        with patch("code_agents.env_loader.GLOBAL_ENV_PATH", tmp_path / "nonexistent"):
            load_all_env(str(repo))

        assert os.environ.get("JENKINS_URL") == "repo-url"

    def test_env_directory_ignored(self, tmp_path, monkeypatch):
        """A .env directory is ignored (not loaded)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env").mkdir()  # directory, not file

        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)

        with patch("code_agents.env_loader.GLOBAL_ENV_PATH", tmp_path / "nonexistent"):
            load_all_env(str(repo))  # should not crash

        assert os.environ["TARGET_REPO_PATH"] == str(repo)

    def test_no_files_still_sets_target(self, tmp_path, monkeypatch):
        """Even with no config files, TARGET_REPO_PATH is set."""
        monkeypatch.delenv("TARGET_REPO_PATH", raising=False)

        with patch("code_agents.env_loader.GLOBAL_ENV_PATH", tmp_path / "nonexistent"):
            load_all_env(str(tmp_path))

        assert os.environ["TARGET_REPO_PATH"] == str(tmp_path)


class TestVarClassification:
    """Verify all expected variables are classified."""

    def test_no_overlap_between_global_and_repo(self):
        assert GLOBAL_VARS & REPO_VARS == set()

    def test_no_overlap_with_runtime(self):
        assert GLOBAL_VARS & RUNTIME_VARS == set()
        assert REPO_VARS & RUNTIME_VARS == set()

    def test_cursor_key_is_global(self):
        assert "CURSOR_API_KEY" in GLOBAL_VARS

    def test_jenkins_is_repo(self):
        assert "JENKINS_URL" in REPO_VARS
        assert "JENKINS_API_TOKEN" in REPO_VARS

    def test_target_repo_path_is_runtime(self):
        assert "TARGET_REPO_PATH" in RUNTIME_VARS
