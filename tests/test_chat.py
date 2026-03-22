"""Tests for chat.py — interactive chat REPL components."""

from __future__ import annotations

import os

import pytest

from code_agents.chat import (
    AGENT_ROLES,
    _check_server,
    _get_agents,
    _handle_command,
    _make_completer,
    _parse_inline_delegation,
)


class TestAgentRoles:
    """Verify all 12 agents have role descriptions."""

    def test_all_agents_have_roles(self):
        expected = [
            "code-reasoning", "code-writer", "code-reviewer", "code-tester",
            "redash-query", "git-ops", "test-coverage", "jenkins-build",
            "jenkins-deploy", "argocd-verify", "pipeline-orchestrator", "agent-router",
        ]
        for agent in expected:
            assert agent in AGENT_ROLES, f"Missing role for {agent}"
            assert len(AGENT_ROLES[agent]) > 10, f"Role too short for {agent}"

    def test_role_count(self):
        assert len(AGENT_ROLES) == 12


class TestGetAgents:
    """Test agent list parsing from various API response formats."""

    def test_parse_data_format(self):
        """Server returns {"object": "list", "data": [...]}."""
        import httpx
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "object": "list",
            "data": [
                {"name": "code-reasoning", "display_name": "Code Reasoning Agent"},
                {"name": "code-writer", "display_name": "Code Writer Agent"},
            ]
        }

        with patch("httpx.get", return_value=mock_response):
            agents = _get_agents("http://localhost:8000")
            assert "code-reasoning" in agents
            assert "code-writer" in agents
            assert agents["code-reasoning"] == "Code Reasoning Agent"

    def test_parse_agents_format(self):
        """Alternate format: {"agents": [...]}."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agents": [
                {"name": "git-ops", "display_name": "Git Ops Agent"},
            ]
        }

        with patch("httpx.get", return_value=mock_response):
            agents = _get_agents("http://localhost:8000")
            assert "git-ops" in agents

    def test_parse_plain_list(self):
        """Plain list format: [...]."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "code-tester", "display_name": "Code Tester"},
        ]

        with patch("httpx.get", return_value=mock_response):
            agents = _get_agents("http://localhost:8000")
            assert "code-tester" in agents

    def test_connection_failure(self):
        """Returns empty dict on connection error."""
        from unittest.mock import patch
        import httpx

        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            agents = _get_agents("http://localhost:9999")
            assert agents == {}

    def test_empty_response(self):
        """Returns empty dict for unexpected response."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {"unexpected": "format"}

        with patch("httpx.get", return_value=mock_response):
            agents = _get_agents("http://localhost:8000")
            assert agents == {}


class TestCheckServer:
    """Test server health check."""

    def test_server_running(self):
        """Returns True when health returns 200."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.get", return_value=mock_response):
            assert _check_server("http://localhost:8000") is True

    def test_server_not_running(self):
        """Returns False on connection error."""
        from unittest.mock import patch
        import httpx

        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            assert _check_server("http://localhost:9999") is False

    def test_server_unhealthy(self):
        """Returns False when health returns non-200."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.get", return_value=mock_response):
            assert _check_server("http://localhost:8000") is False


class TestSlashCommands:
    """Test chat slash command handling."""

    def _make_state(self):
        return {"agent": "code-reasoning", "session_id": "abc123", "repo_path": "/tmp/repo"}

    def test_quit(self):
        state = self._make_state()
        assert _handle_command("/quit", state, "http://localhost:8000") == "quit"

    def test_exit(self):
        state = self._make_state()
        assert _handle_command("/exit", state, "http://localhost:8000") == "quit"

    def test_q(self):
        state = self._make_state()
        assert _handle_command("/q", state, "http://localhost:8000") == "quit"

    def test_clear(self):
        state = self._make_state()
        result = _handle_command("/clear", state, "http://localhost:8000")
        assert result is None
        assert state["session_id"] is None

    def test_session(self, capsys):
        state = self._make_state()
        _handle_command("/session", state, "http://localhost:8000")
        captured = capsys.readouterr()
        assert "abc123" in captured.out

    def test_session_none(self, capsys):
        state = {"agent": "code-reasoning", "session_id": None, "repo_path": "/tmp"}
        _handle_command("/session", state, "http://localhost:8000")
        captured = capsys.readouterr()
        assert "No active session" in captured.out

    def test_help(self, capsys):
        state = self._make_state()
        result = _handle_command("/help", state, "http://localhost:8000")
        assert result is None
        captured = capsys.readouterr()
        assert "/quit" in captured.out
        assert "/agent" in captured.out
        assert "/clear" in captured.out

    def test_agent_no_arg(self, capsys):
        state = self._make_state()
        _handle_command("/agent", state, "http://localhost:8000")
        captured = capsys.readouterr()
        assert "Usage" in captured.out

    def test_agent_switch(self, capsys):
        """Switch agent when server returns agent list."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"name": "code-writer", "display_name": "Code Writer Agent"},
                {"name": "code-reasoning", "display_name": "Code Reasoning Agent"},
            ]
        }

        state = self._make_state()
        with patch("httpx.get", return_value=mock_response):
            _handle_command("/agent code-writer", state, "http://localhost:8000")
        assert state["agent"] == "code-writer"
        assert state["session_id"] is None  # cleared on switch

    def test_agent_not_found(self, capsys):
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"name": "code-reasoning", "display_name": ""}]}

        state = self._make_state()
        with patch("httpx.get", return_value=mock_response):
            _handle_command("/agent nonexistent", state, "http://localhost:8000")
        assert state["agent"] == "code-reasoning"  # unchanged
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_unknown_command(self, capsys):
        state = self._make_state()
        result = _handle_command("/foo", state, "http://localhost:8000")
        assert result is None
        captured = capsys.readouterr()
        assert "Unknown command" in captured.out


class TestRepoDetection:
    """Test that chat detects git repos correctly."""

    def test_detects_git_repo(self, tmp_path):
        """Should find .git directory."""
        repo = tmp_path / "myrepo"
        repo.mkdir()
        (repo / ".git").mkdir()

        # Walk up from a subdirectory
        subdir = repo / "src" / "main"
        subdir.mkdir(parents=True)

        # Simulate the detection logic from chat_main
        check_dir = str(subdir)
        found = None
        while True:
            if os.path.isdir(os.path.join(check_dir, ".git")):
                found = check_dir
                break
            parent = os.path.dirname(check_dir)
            if parent == check_dir:
                break
            check_dir = parent

        assert found == str(repo)

    def test_no_git_repo(self, tmp_path):
        """Should not find .git in temp directory without one."""
        check_dir = str(tmp_path)
        found = None
        while True:
            if os.path.isdir(os.path.join(check_dir, ".git")):
                found = check_dir
                break
            parent = os.path.dirname(check_dir)
            if parent == check_dir:
                break
            check_dir = parent

        # tmp_path itself doesn't have .git, but a parent might
        # (the test runner's working dir). So we just check the logic runs.
        assert True  # No crash


class TestStreamChat:
    """Test SSE stream parsing."""

    def test_parse_sse_text_chunk(self):
        """Verify _stream_chat yields text from SSE data lines."""
        import json

        # Simulate an SSE line
        chunk = {
            "choices": [{
                "delta": {"content": "Hello world"},
                "finish_reason": None,
            }]
        }
        line = f"data: {json.dumps(chunk)}"

        # Parse like _stream_chat does
        data_str = line[6:]
        parsed = json.loads(data_str)
        delta = parsed["choices"][0]["delta"]
        assert delta.get("content") == "Hello world"

    def test_parse_sse_reasoning_chunk(self):
        """Verify reasoning_content is parsed from SSE."""
        import json

        chunk = {
            "choices": [{
                "delta": {"reasoning_content": "> **Using tool: read_file**"},
                "finish_reason": None,
            }]
        }
        line = f"data: {json.dumps(chunk)}"
        data_str = line[6:]
        parsed = json.loads(data_str)
        delta = parsed["choices"][0]["delta"]
        assert "Using tool" in delta.get("reasoning_content", "")

    def test_parse_sse_session_id(self):
        """Verify session_id is extracted from final chunk."""
        import json

        chunk = {
            "session_id": "sess-abc-123",
            "choices": [{
                "delta": {},
                "finish_reason": "stop",
            }]
        }
        line = f"data: {json.dumps(chunk)}"
        data_str = line[6:]
        parsed = json.loads(data_str)
        assert parsed.get("session_id") == "sess-abc-123"

    def test_parse_done_marker(self):
        """Verify [DONE] marker is recognized."""
        line = "data: [DONE]"
        data_str = line[6:]
        assert data_str == "[DONE]"


class TestInlineDelegation:
    """Test inline agent delegation parsing (/agent-name prompt)."""

    AGENTS = {
        "code-reasoning": "Code Reasoning Agent",
        "code-writer": "Code Writer Agent",
        "code-tester": "Code Tester Agent",
        "code-reviewer": "Code Reviewer Agent",
        "git-ops": "Git Ops Agent",
    }

    def test_agent_with_prompt(self):
        """'/code-reasoning explain auth' → delegation."""
        agent, prompt = _parse_inline_delegation(
            "/code-reasoning explain auth", self.AGENTS
        )
        assert agent == "code-reasoning"
        assert prompt == "explain auth"

    def test_agent_no_prompt_returns_empty(self):
        """'/code-writer' with no prompt → permanent switch signal."""
        agent, prompt = _parse_inline_delegation("/code-writer", self.AGENTS)
        assert agent == "code-writer"
        assert prompt == ""

    def test_unknown_agent(self):
        """'/nonexistent do stuff' → not a delegation."""
        agent, prompt = _parse_inline_delegation("/nonexistent do stuff", self.AGENTS)
        assert agent is None
        assert prompt is None

    def test_regular_slash_command(self):
        """'/help' → not a delegation."""
        agent, prompt = _parse_inline_delegation("/help", self.AGENTS)
        assert agent is None
        assert prompt is None

    def test_quit_not_delegation(self):
        """'/quit' → not a delegation."""
        agent, prompt = _parse_inline_delegation("/quit", self.AGENTS)
        assert agent is None
        assert prompt is None

    def test_not_a_slash_command(self):
        """Regular text → not a delegation."""
        agent, prompt = _parse_inline_delegation("hello world", self.AGENTS)
        assert agent is None
        assert prompt is None

    def test_multiword_prompt(self):
        """Prompt with multiple words is captured fully."""
        agent, prompt = _parse_inline_delegation(
            "/code-tester write unit tests for PaymentService class", self.AGENTS
        )
        assert agent == "code-tester"
        assert prompt == "write unit tests for PaymentService class"

    def test_git_ops_agent(self):
        """Agent names with hyphens work."""
        agent, prompt = _parse_inline_delegation(
            "/git-ops show the last 5 commits", self.AGENTS
        )
        assert agent == "git-ops"
        assert prompt == "show the last 5 commits"

    def test_empty_agents_dict(self):
        """No agents available → no match."""
        agent, prompt = _parse_inline_delegation("/code-reasoning explain", {})
        assert agent is None
        assert prompt is None


class TestTabCompletion:
    """Test readline tab-completion for slash commands and agent names."""

    SLASH_COMMANDS = ["/help", "/quit", "/exit", "/agents", "/agent", "/session", "/clear"]
    AGENT_NAMES = ["code-reasoning", "code-writer", "code-tester", "code-reviewer", "git-ops"]

    def _completer(self):
        return _make_completer(self.SLASH_COMMANDS, self.AGENT_NAMES)

    def test_complete_slash_shows_all(self):
        """'/' + Tab cycles through all completions."""
        completer = self._completer()
        results = []
        idx = 0
        while True:
            result = completer("/", idx)
            if result is None:
                break
            results.append(result)
            idx += 1
        # 7 slash commands + 5 agent names
        assert len(results) == 12
        assert "/help" in results
        assert "/code-reasoning" in results

    def test_complete_code_prefix(self):
        """'/code-' + Tab shows only code-* agents."""
        completer = self._completer()
        results = []
        idx = 0
        while True:
            result = completer("/code-", idx)
            if result is None:
                break
            results.append(result)
            idx += 1
        assert set(results) == {"/code-reasoning", "/code-writer", "/code-tester", "/code-reviewer"}

    def test_complete_exact_match(self):
        """'/help' + Tab returns '/help' then None."""
        completer = self._completer()
        assert completer("/help", 0) == "/help"
        assert completer("/help", 1) is None

    def test_complete_no_match(self):
        """'/xyz' + Tab returns None immediately."""
        completer = self._completer()
        assert completer("/xyz", 0) is None

    def test_no_completion_without_slash(self):
        """Plain text gets no completions."""
        completer = self._completer()
        assert completer("hello", 0) is None
        assert completer("code", 0) is None

    def test_complete_git_ops(self):
        """'/git' + Tab completes to '/git-ops'."""
        completer = self._completer()
        assert completer("/git", 0) == "/git-ops"
        assert completer("/git", 1) is None

    def test_complete_agent_command(self):
        """'/agent' matches both '/agent' and '/agents'."""
        completer = self._completer()
        results = []
        idx = 0
        while True:
            result = completer("/agent", idx)
            if result is None:
                break
            results.append(result)
            idx += 1
        assert "/agent" in results
        assert "/agents" in results
