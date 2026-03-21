"""Tests for git_client.py — async git operations."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from code_agents.git_client import GitClient, GitOpsError, _validate_ref


# --- Unit tests (no git repo needed) ---


class TestValidateRef:
    def test_valid_refs(self):
        for ref in ("main", "feature/foo", "release-1.0", "v1.2.3", "HEAD"):
            _validate_ref(ref)  # should not raise

    def test_invalid_refs(self):
        for ref in ("", "branch name", "foo;rm -rf /", "$(whoami)", "a\nb"):
            with pytest.raises(GitOpsError, match="Invalid"):
                _validate_ref(ref)


# --- Integration tests (use a real temporary git repo) ---


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary git repo with an initial commit."""
    repo = str(tmp_path / "repo")
    os.makedirs(repo)

    def run(cmd):
        result = os.popen(f"cd {repo} && {cmd} 2>&1").read()
        return result

    run("git init")
    run("git config user.email 'test@test.com'")
    run("git config user.name 'Test'")
    # Create initial commit on main
    run("echo 'hello' > file1.txt")
    run("git add file1.txt")
    run("git commit -m 'initial commit'")
    # Rename default branch to main if needed
    run("git branch -M main")
    return repo


class TestGitClient:
    def test_current_branch(self, tmp_repo):
        client = GitClient(tmp_repo)
        branch = asyncio.run(client.current_branch())
        assert branch == "main"

    def test_list_branches(self, tmp_repo):
        client = GitClient(tmp_repo)
        branches = asyncio.run(client.list_branches())
        names = [b["name"] for b in branches]
        assert "main" in names

    def test_log(self, tmp_repo):
        client = GitClient(tmp_repo)
        commits = asyncio.run(client.log("main"))
        assert len(commits) >= 1
        assert commits[0]["message"] == "initial commit"

    def test_status_clean(self, tmp_repo):
        client = GitClient(tmp_repo)
        status = asyncio.run(client.status())
        assert status["clean"] is True

    def test_status_dirty(self, tmp_repo):
        # Create an untracked file
        with open(os.path.join(tmp_repo, "new.txt"), "w") as f:
            f.write("new")
        client = GitClient(tmp_repo)
        status = asyncio.run(client.status())
        assert status["clean"] is False
        assert any(f["file"] == "new.txt" for f in status["files"])

    def test_diff(self, tmp_repo):
        # Create a feature branch with changes
        os.popen(f"cd {tmp_repo} && git checkout -b feature 2>&1").read()
        with open(os.path.join(tmp_repo, "file2.txt"), "w") as f:
            f.write("new file content\n")
        os.popen(f"cd {tmp_repo} && git add file2.txt && git commit -m 'add file2' 2>&1").read()

        client = GitClient(tmp_repo)
        diff = asyncio.run(client.diff("main", "feature"))
        assert diff["files_changed"] >= 1
        assert diff["insertions"] >= 1
        assert any("file2.txt" in f["file"] for f in diff["changed_files"])

    def test_diff_invalid_ref(self, tmp_repo):
        client = GitClient(tmp_repo)
        with pytest.raises(GitOpsError, match="Invalid"):
            asyncio.run(client.diff("main", "bad;ref"))

    def test_log_invalid_branch(self, tmp_repo):
        client = GitClient(tmp_repo)
        with pytest.raises(GitOpsError, match="Invalid"):
            asyncio.run(client.log("$(whoami)"))
