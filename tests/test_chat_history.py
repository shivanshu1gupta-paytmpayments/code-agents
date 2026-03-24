"""Tests for chat_history module and stream.build_prompt."""

import time
from unittest.mock import patch

import pytest

from code_agents.chat_history import (
    _make_title,
    add_message,
    create_session,
    delete_session,
    list_sessions,
    load_session,
)


# ---------------------------------------------------------------------------
# _make_title
# ---------------------------------------------------------------------------


class TestMakeTitle:
    def test_short_message(self):
        assert _make_title("Hello world") == "Hello world"

    def test_long_message(self):
        title = _make_title("A" * 100)
        assert len(title) <= 60
        assert title.endswith("...")

    def test_multiline(self):
        assert _make_title("First line\nSecond line") == "First line"

    def test_empty(self):
        assert _make_title("") == "Untitled"

    def test_whitespace(self):
        assert _make_title("   ") == "Untitled"


# ---------------------------------------------------------------------------
# Session CRUD (uses a temp directory)
# ---------------------------------------------------------------------------


class TestSessionCRUD:
    @pytest.fixture(autouse=True)
    def _use_temp_dir(self, tmp_path):
        with patch("code_agents.chat_history.HISTORY_DIR", tmp_path):
            with patch("code_agents.chat_history._ensure_dir", return_value=tmp_path):
                self.tmp = tmp_path
                yield

    def test_create_session(self):
        session = create_session("code-writer", "/tmp/repo")
        assert session["agent"] == "code-writer"
        assert session["repo_path"] == "/tmp/repo"
        assert session["title"] == "New chat"
        assert len(session["messages"]) == 0
        # Full UUID format (contains dashes)
        assert "-" in session["id"]

    def test_create_with_custom_id(self):
        session = create_session("code-writer", "/tmp/repo", session_id="custom-123")
        assert session["id"] == "custom-123"

    def test_load_session(self):
        session = create_session("code-writer", "/tmp/repo")
        loaded = load_session(session["id"])
        assert loaded is not None
        assert loaded["id"] == session["id"]
        assert loaded["agent"] == "code-writer"

    def test_load_nonexistent(self):
        assert load_session("nonexistent") is None

    def test_add_message(self):
        session = create_session("code-writer", "/tmp/repo")
        add_message(session, "user", "Hello")
        assert len(session["messages"]) == 1
        assert session["messages"][0]["role"] == "user"
        assert session["messages"][0]["content"] == "Hello"
        assert "timestamp" in session["messages"][0]

    def test_add_message_sets_title(self):
        session = create_session("code-writer", "/tmp/repo")
        assert session["title"] == "New chat"
        add_message(session, "user", "Fix the login bug")
        assert session["title"] == "Fix the login bug"

    def test_title_not_overwritten(self):
        session = create_session("code-writer", "/tmp/repo")
        add_message(session, "user", "First message")
        add_message(session, "user", "Second message")
        assert session["title"] == "First message"

    def test_delete_session(self):
        session = create_session("code-writer", "/tmp/repo")
        assert delete_session(session["id"]) is True
        assert load_session(session["id"]) is None

    def test_delete_nonexistent(self):
        assert delete_session("nonexistent") is False

    def test_list_sessions_empty(self):
        assert list_sessions() == []

    def test_list_sessions(self):
        create_session("code-writer", "/tmp/repo")
        create_session("code-tester", "/tmp/repo")
        sessions = list_sessions()
        assert len(sessions) == 2

    def test_list_sessions_sorted_recent_first(self):
        s1 = create_session("code-writer", "/tmp/repo")
        time.sleep(0.02)
        s2 = create_session("code-tester", "/tmp/repo")
        sessions = list_sessions()
        assert sessions[0]["id"] == s2["id"]  # most recent first
        assert sessions[1]["id"] == s1["id"]

    def test_list_sessions_filter_by_repo(self):
        create_session("code-writer", "/tmp/repo1")
        create_session("code-tester", "/tmp/repo2")
        sessions = list_sessions(repo_path="/tmp/repo1")
        assert len(sessions) == 1
        assert sessions[0]["agent"] == "code-writer"

    def test_list_sessions_limit(self):
        for _ in range(5):
            create_session("code-writer", "/tmp/repo")
        sessions = list_sessions(limit=3)
        assert len(sessions) == 3

    def test_persistence(self):
        """Messages persist to disk and can be reloaded."""
        session = create_session("code-writer", "/tmp/repo")
        add_message(session, "user", "Hello")
        add_message(session, "assistant", "Hi there!")

        loaded = load_session(session["id"])
        assert len(loaded["messages"]) == 2
        assert loaded["messages"][0]["content"] == "Hello"
        assert loaded["messages"][1]["content"] == "Hi there!"


# ---------------------------------------------------------------------------
# build_prompt (from stream.py)
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_single_message(self):
        from code_agents.stream import build_prompt
        from code_agents.models import Message

        messages = [Message(role="user", content="Hello")]
        assert build_prompt(messages) == "Hello"

    def test_multi_turn(self):
        from code_agents.stream import build_prompt
        from code_agents.models import Message

        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
            Message(role="user", content="How are you?"),
        ]
        result = build_prompt(messages)
        assert "Human: Hello" in result
        assert "Assistant: Hi there!" in result
        assert "Human: How are you?" in result

    def test_system_messages_filtered(self):
        from code_agents.stream import build_prompt
        from code_agents.models import Message

        messages = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello"),
        ]
        result = build_prompt(messages)
        assert result == "Hello"
        assert "system" not in result.lower()

    def test_empty_messages(self):
        from code_agents.stream import build_prompt

        assert build_prompt([]) == ""