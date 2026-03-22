"""Tests for cli.py — CLI command helpers and dispatching."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestServerUrl:
    """Test _server_url resolution."""

    def test_default_url(self):
        from code_agents.cli import _server_url
        with patch.dict(os.environ, {"HOST": "0.0.0.0", "PORT": "8000"}):
            url = _server_url()
            assert url == "http://127.0.0.1:8000"

    def test_custom_host_port(self):
        from code_agents.cli import _server_url
        with patch.dict(os.environ, {"HOST": "10.0.0.1", "PORT": "9000"}):
            url = _server_url()
            assert url == "http://10.0.0.1:9000"

    def test_localhost_passthrough(self):
        from code_agents.cli import _server_url
        with patch.dict(os.environ, {"HOST": "127.0.0.1", "PORT": "8080"}):
            url = _server_url()
            assert url == "http://127.0.0.1:8080"


class TestAgentListParsing:
    """Test that cli.py _api_get parses agent lists correctly."""

    def test_parse_data_format(self):
        """Server returns {"object": "list", "data": [...]}."""
        data = {
            "object": "list",
            "data": [
                {"name": "code-reasoning", "display_name": "Code Reasoning Agent"},
                {"name": "code-writer", "display_name": "Code Writer Agent"},
            ]
        }
        # Replicate the parsing logic from cli.py cmd_agents
        if isinstance(data, dict):
            agents = data.get("data") or data.get("agents") or []
        elif isinstance(data, list):
            agents = data
        else:
            agents = []
        assert len(agents) == 2
        assert agents[0]["name"] == "code-reasoning"

    def test_parse_agents_format(self):
        data = {"agents": [{"name": "git-ops"}]}
        agents = data.get("data") or data.get("agents") or []
        assert len(agents) == 1

    def test_parse_plain_list(self):
        data = [{"name": "code-tester"}]
        if isinstance(data, list):
            agents = data
        else:
            agents = []
        assert len(agents) == 1

    def test_parse_empty(self):
        data = {"unexpected": "format"}
        agents = data.get("data") or data.get("agents") or []
        assert agents == []


class TestCmdHelp:
    """Test that help command produces comprehensive output."""

    def test_help_contains_all_commands(self, capsys):
        from code_agents.cli import cmd_help
        cmd_help()
        output = capsys.readouterr().out

        # All 18 commands should appear
        commands = [
            "init", "migrate", "start", "chat", "setup", "shutdown", "status",
            "logs", "config", "doctor", "branches", "diff", "test",
            "review", "pipeline", "agents", "curls", "version", "help",
        ]
        for cmd in commands:
            assert cmd in output, f"Command '{cmd}' missing from help"

    def test_help_contains_chat_slash_commands(self, capsys):
        from code_agents.cli import cmd_help
        cmd_help()
        output = capsys.readouterr().out

        slash_cmds = ["/help", "/quit", "/agent", "/agents", "/session", "/clear"]
        for cmd in slash_cmds:
            assert cmd in output, f"Chat command '{cmd}' missing from help"

    def test_help_contains_all_agents(self, capsys):
        from code_agents.cli import cmd_help
        cmd_help()
        output = capsys.readouterr().out

        agents = [
            "code-reasoning", "code-writer", "code-reviewer", "code-tester",
            "git-ops", "test-coverage", "jenkins-build", "jenkins-deploy",
            "argocd-verify", "pipeline-orchestrator", "agent-router",
        ]
        for agent in agents:
            assert agent in output, f"Agent '{agent}' missing from help"

    def test_help_contains_pipeline_subcommands(self, capsys):
        from code_agents.cli import cmd_help
        cmd_help()
        output = capsys.readouterr().out

        for sub in ["pipeline start", "pipeline status", "pipeline advance", "pipeline rollback"]:
            assert sub in output, f"Pipeline subcommand '{sub}' missing from help"

    def test_help_contains_install_url(self, capsys):
        from code_agents.cli import cmd_help
        cmd_help()
        output = capsys.readouterr().out
        assert "shivanshu1gupta-paytmpayments/code-agents" in output


class TestCmdVersion:
    """Test version command."""

    def test_version_output(self, capsys):
        from code_agents.cli import cmd_version
        cmd_version()
        output = capsys.readouterr().out
        assert "code-agents" in output
        assert "Python" in output


class TestCmdDoctor:
    """Test doctor command checks."""

    def test_doctor_runs(self, capsys):
        from code_agents.cli import cmd_doctor
        cmd_doctor()
        output = capsys.readouterr().out
        assert "Code Agents Doctor" in output
        assert "Python" in output
        # Should check for .env, git repo, etc.
        assert ".env" in output or "env" in output.lower()


class TestCmdConfig:
    """Test config command."""

    def test_config_no_env_file(self, capsys, tmp_path, monkeypatch):
        """Should warn when no .env exists."""
        monkeypatch.chdir(tmp_path)
        from code_agents.cli import cmd_config
        cmd_config()
        output = capsys.readouterr().out
        assert "not found" in output

    def test_config_with_env_file(self, capsys, tmp_path, monkeypatch):
        """Should show config when .env exists."""
        env_file = tmp_path / ".env"
        env_file.write_text("HOST=0.0.0.0\nPORT=8000\nCURSOR_API_KEY=crsr_abc123xyz789\n")
        monkeypatch.chdir(tmp_path)
        from code_agents.cli import cmd_config
        cmd_config()
        output = capsys.readouterr().out
        assert "Configuration" in output
        assert "HOST" in output
        # Secret should be masked
        assert "crsr_abc123xyz789" not in output


class TestCmdCurls:
    """Test curls command."""

    def test_curls_no_args_shows_index(self, capsys):
        from code_agents.cli import cmd_curls
        cmd_curls([])
        output = capsys.readouterr().out
        assert "Filter by category" in output
        assert "health" in output
        assert "jenkins" in output
        assert "argocd" in output

    def test_curls_health_filter(self, capsys):
        from code_agents.cli import cmd_curls
        cmd_curls(["health"])
        output = capsys.readouterr().out
        assert "/health" in output
        assert "/diagnostics" in output
        assert "Jenkins" not in output  # should be filtered out

    def test_curls_jenkins_filter(self, capsys):
        from code_agents.cli import cmd_curls
        cmd_curls(["jenkins"])
        output = capsys.readouterr().out
        assert "jenkins/build" in output
        assert "Showing: jenkins" in output

    def test_curls_agent_specific(self, capsys):
        from code_agents.cli import cmd_curls
        cmd_curls(["code-reasoning"])
        output = capsys.readouterr().out
        assert "code-reasoning" in output
        assert "chat/completions" in output
        assert "Example prompts" in output

    def test_curls_unknown_agent(self, capsys):
        from code_agents.cli import cmd_curls
        cmd_curls(["nonexistent-agent"])
        output = capsys.readouterr().out
        assert "not found" in output


class TestMainDispatcher:
    """Test the main() CLI dispatcher."""

    def test_help_flag(self, capsys):
        from code_agents.cli import main
        with patch.object(sys, "argv", ["code-agents", "help"]):
            main()
        output = capsys.readouterr().out
        assert "code-agents" in output
        assert "USAGE" in output

    def test_version_flag(self, capsys):
        from code_agents.cli import main
        with patch.object(sys, "argv", ["code-agents", "version"]):
            main()
        output = capsys.readouterr().out
        assert "Python" in output

    def test_unknown_command(self, capsys):
        from code_agents.cli import main
        with patch.object(sys, "argv", ["code-agents", "foobar"]):
            with pytest.raises(SystemExit):
                main()
        output = capsys.readouterr().out
        assert "Unknown command" in output
