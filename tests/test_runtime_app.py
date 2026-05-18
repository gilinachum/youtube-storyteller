"""Tests for runtime_app — payload parsing, session management, streaming."""

import os
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from moto import mock_aws
import boto3

os.environ["MESSAGES_TABLE"] = "test-messages"
os.environ["SESSIONS_TABLE"] = "test-sessions"
os.environ["UPLOAD_BUCKET"] = "test-uploads"


class TestParsePayload:
    """Test the _parse_payload helper."""

    def test_valid_payload(self):
        from agent.runtime_app import _parse_payload

        email, msg, sid, refs, prompt = _parse_payload({
            "email": "Test@Example.COM",
            "message": "hello",
            "session_id": "s1",
        })
        assert email == "test@example.com"  # normalized
        assert msg == "hello"
        assert sid == "s1"
        assert refs == []
        assert prompt == "hello"

    def test_payload_with_files(self):
        from agent.runtime_app import _parse_payload

        _, _, _, refs, prompt = _parse_payload({
            "email": "a@b.com",
            "message": "analyze",
            "session_id": "s1",
            "file_refs": [{"filename": "doc.pdf", "s3_key": "uploads/doc.pdf"}],
        })
        assert len(refs) == 1
        assert "קובץ מצורף" in prompt
        assert "doc.pdf" in prompt

    def test_missing_email(self):
        from agent.runtime_app import _parse_payload

        with pytest.raises(ValueError, match="email"):
            _parse_payload({"message": "hi", "session_id": "s1"})

    def test_missing_message(self):
        from agent.runtime_app import _parse_payload

        with pytest.raises(ValueError, match="message"):
            _parse_payload({"email": "a@b.com", "session_id": "s1"})

    def test_missing_session_id(self):
        from agent.runtime_app import _parse_payload

        with pytest.raises(ValueError, match="session_id"):
            _parse_payload({"email": "a@b.com", "message": "hi"})

    def test_empty_strings_rejected(self):
        from agent.runtime_app import _parse_payload

        with pytest.raises(ValueError):
            _parse_payload({"email": "  ", "message": "hi", "session_id": "s1"})


class TestSessionManagement:
    """Test DynamoDB session and message persistence."""

    @mock_aws
    def test_save_and_load_messages(self):
        # Create table
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName="test-messages",
            KeySchema=[
                {"AttributeName": "session_id", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Need to reimport after moto is active
        import importlib
        import agent.runtime_app as rt
        # Patch the dynamodb resource to use mocked one
        rt.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        rt._save_message("sess-1", "user", "hello", "2026-01-01T00:00:00Z")
        rt._save_message("sess-1", "assistant", "hi back", "2026-01-01T00:00:01Z")

        history = rt._load_history("sess-1")
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "hello"
        assert history[1]["role"] == "assistant"

    @mock_aws
    def test_ensure_session_creates_new(self):
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName="test-sessions",
            KeySchema=[
                {"AttributeName": "email", "KeyType": "HASH"},
                {"AttributeName": "session_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "email", "AttributeType": "S"},
                {"AttributeName": "session_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        import agent.runtime_app as rt
        rt.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        rt._ensure_session("test@example.com", "sess-new", "2026-01-01T00:00:00Z")

        table = rt.dynamodb.Table("test-sessions")
        resp = table.get_item(Key={"email": "test@example.com", "session_id": "sess-new"})
        assert "Item" in resp
        assert resp["Item"]["name"] == "שיחה חדשה"

    @mock_aws
    def test_ensure_session_updates_existing(self):
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName="test-sessions",
            KeySchema=[
                {"AttributeName": "email", "KeyType": "HASH"},
                {"AttributeName": "session_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "email", "AttributeType": "S"},
                {"AttributeName": "session_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        import agent.runtime_app as rt
        rt.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        rt._ensure_session("t@t.com", "s1", "2026-01-01T00:00:00Z")
        rt._ensure_session("t@t.com", "s1", "2026-01-01T01:00:00Z")  # should update, not fail

        table = rt.dynamodb.Table("test-sessions")
        resp = table.get_item(Key={"email": "t@t.com", "session_id": "s1"})
        assert resp["Item"]["updated_at"] == "2026-01-01T01:00:00Z"


class TestHistoryInjection:
    """Test injecting DynamoDB history into Strands agent."""

    def test_inject_history(self):
        from agent.runtime_app import _inject_history

        mock_agent = MagicMock()
        mock_agent.messages = []

        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

        _inject_history(mock_agent, history)

        assert len(mock_agent.messages) == 2
        assert mock_agent.messages[0]["role"] == "user"
        assert mock_agent.messages[0]["content"] == [{"text": "hello"}]
        assert mock_agent.messages[1]["role"] == "assistant"


class TestAgentCache:
    """Test the in-process agent cache."""

    @mock_aws
    def test_cold_start_creates_agent(self):
        # Setup tables
        client = boto3.client("dynamodb", region_name="us-east-1")
        for table_name, keys in [
            ("test-messages", [("session_id", "HASH"), ("timestamp", "RANGE")]),
        ]:
            client.create_table(
                TableName=table_name,
                KeySchema=[{"AttributeName": k, "KeyType": t} for k, t in keys],
                AttributeDefinitions=[{"AttributeName": k, "AttributeType": "S"} for k, _ in keys],
                BillingMode="PAY_PER_REQUEST",
            )

        import agent.runtime_app as rt
        rt.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        rt._agents.clear()

        with patch("agent.runtime_app.create_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.messages = []
            mock_create.return_value = mock_agent

            agent = rt._get_or_create_agent("a@b.com", "s1")
            mock_create.assert_called_once_with(email="a@b.com", session_id="s1", user_message=None)
            assert "a@b.com:s1" in rt._agents

            # Second call should use cache
            mock_create.reset_mock()
            agent2 = rt._get_or_create_agent("a@b.com", "s1")
            assert not mock_create.called
            assert agent2 is agent


class TestStreamingFormat:
    """Test that progress events use correct JSON format."""

    def test_progress_json_has_hebrew_labels(self):
        """Progress labels should be UTF-8, not unicode-escaped."""
        tool_labels = {
            "web_research": "🔍 מחפש באינטרנט...",
            "pdf_extract": "📄 מנתח קובץ PDF...",
            "trend_analysis": "📈 בודק טרנדים...",
        }
        for tool, label in tool_labels.items():
            encoded = json.dumps({"type": "progress", "tool": tool, "label": label}, ensure_ascii=False)
            assert "\\u05" not in encoded  # No unicode escapes
            assert label in encoded  # Hebrew appears as-is
