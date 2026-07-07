"""Tests for session pinning & ownership — the critical auth path.

Covers:
- _ensure_session: composite key prevents cross-user access
- _get_or_create_agent: cache hit/miss behavior
- _extract_email_from_jwt: JWT parsing from Authorization header
- Session isolation: user A cannot access user B's session data
"""

import os
import sys
import json
import base64
import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from moto import mock_aws
import boto3

os.environ.setdefault("MESSAGES_TABLE", "test-messages")
os.environ.setdefault("SESSIONS_TABLE", "test-sessions")
os.environ.setdefault("UPLOAD_BUCKET", "test-uploads")
# Pin the region to match every boto3.resource(...) call in this file (all use
# us-east-1 explicitly below). agent/runtime_app.py binds its module-level
# `dynamodb` resource ONCE at first import time, reading AWS_REGION /
# AWS_DEFAULT_REGION (default us-west-2) — if some other test file imports
# agent.runtime_app first with a different region resolved, this file's tables
# (created in us-east-1) would silently mismatch and every _ensure_session()
# call would fail with ResourceNotFoundException. setdefault() here only takes
# effect if nothing set these yet; explicit pins in other test files still win
# per normal import-order rules, but this guarantees OUR file is internally
# consistent when run first or standalone.
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")




def _make_jwt(claims: dict) -> str:
    """Create a fake JWT with given payload claims (no signature verification needed)."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(b"fake-signature").rstrip(b"=").decode()
    return f"{header}.{payload}.{signature}"


class TestEnsureSession:
    """Test _ensure_session — DDB composite key ownership model."""

    @mock_aws
    def test_creates_new_session(self):
        """First call creates a session record owned by the email."""
        self._setup_table()
        from agent.runtime_app import _ensure_session

        _ensure_session("alice@example.com", "session-001", "2026-01-01T00:00:00Z")

        table = boto3.resource("dynamodb", region_name="us-east-1").Table("test-sessions")
        item = table.get_item(Key={"email": "alice@example.com", "session_id": "session-001"}).get("Item")
        assert item is not None
        assert item["email"] == "alice@example.com"
        assert item["session_id"] == "session-001"
        assert item["status"] == "active"

    @mock_aws
    def test_updates_existing_session(self):
        """Second call updates updated_at without overwriting."""
        self._setup_table()
        from agent.runtime_app import _ensure_session

        _ensure_session("alice@example.com", "session-001", "2026-01-01T00:00:00Z")
        _ensure_session("alice@example.com", "session-001", "2026-01-01T01:00:00Z")

        table = boto3.resource("dynamodb", region_name="us-east-1").Table("test-sessions")
        item = table.get_item(Key={"email": "alice@example.com", "session_id": "session-001"}).get("Item")
        assert item["updated_at"] == "2026-01-01T01:00:00Z"
        assert item["created_at"] == "2026-01-01T00:00:00Z"  # Not overwritten

    @mock_aws
    def test_cross_user_creates_separate_session(self):
        """User B sending user A's session_id creates a NEW record under B's email."""
        self._setup_table()
        from agent.runtime_app import _ensure_session

        # Alice creates session-001
        _ensure_session("alice@example.com", "session-001", "2026-01-01T00:00:00Z")

        # Bob sends session-001 (malicious or accidental)
        _ensure_session("bob@example.com", "session-001", "2026-01-01T00:00:00Z")

        table = boto3.resource("dynamodb", region_name="us-east-1").Table("test-sessions")

        # Both exist independently
        alice_item = table.get_item(Key={"email": "alice@example.com", "session_id": "session-001"}).get("Item")
        bob_item = table.get_item(Key={"email": "bob@example.com", "session_id": "session-001"}).get("Item")
        assert alice_item is not None
        assert bob_item is not None
        assert alice_item["email"] == "alice@example.com"
        assert bob_item["email"] == "bob@example.com"

    @mock_aws
    def test_user_cannot_modify_other_users_session(self):
        """Updating with wrong email doesn't touch the other user's record."""
        self._setup_table()
        from agent.runtime_app import _ensure_session

        _ensure_session("alice@example.com", "session-001", "2026-01-01T00:00:00Z")
        _ensure_session("bob@example.com", "session-001", "2026-01-01T02:00:00Z")

        table = boto3.resource("dynamodb", region_name="us-east-1").Table("test-sessions")
        alice_item = table.get_item(Key={"email": "alice@example.com", "session_id": "session-001"}).get("Item")
        # Alice's record unchanged by Bob's call
        assert alice_item["updated_at"] == "2026-01-01T00:00:00Z"

    def _setup_table(self):
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
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "session-id-index",
                    "KeySchema": [{"AttributeName": "session_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )


class TestExtractEmailFromJwt:
    """Test JWT email extraction from Authorization header."""

    def test_valid_jwt_with_email(self):
        from agent.runtime_app import _extract_email_from_jwt

        token = _make_jwt({"email": "user@example.com", "sub": "user-uuid"})
        context = MagicMock()
        context.request_headers = {"Authorization": f"Bearer {token}"}

        email = _extract_email_from_jwt(context)
        assert email == "user@example.com"

    def test_falls_back_to_sub_claim(self):
        from agent.runtime_app import _extract_email_from_jwt

        token = _make_jwt({"sub": "fallback@example.com"})
        context = MagicMock()
        context.request_headers = {"Authorization": f"Bearer {token}"}

        email = _extract_email_from_jwt(context)
        assert email == "fallback@example.com"

    def test_missing_auth_header(self):
        from agent.runtime_app import _extract_email_from_jwt

        context = MagicMock()
        context.request_headers = {}

        email = _extract_email_from_jwt(context)
        assert email == ""

    def test_invalid_jwt_format(self):
        from agent.runtime_app import _extract_email_from_jwt

        context = MagicMock()
        context.request_headers = {"Authorization": "Bearer not-a-jwt"}

        email = _extract_email_from_jwt(context)
        assert email == ""

    def test_lowercase_auth_header(self):
        """Headers may come lowercase from some proxies."""
        from agent.runtime_app import _extract_email_from_jwt

        token = _make_jwt({"email": "USER@Example.COM"})
        context = MagicMock()
        context.request_headers = {"authorization": f"Bearer {token}"}

        email = _extract_email_from_jwt(context)
        assert email == "user@example.com"

    def test_fallback_to_starlette_request(self):
        """Falls back to context.request.headers if request_headers is empty."""
        from agent.runtime_app import _extract_email_from_jwt

        token = _make_jwt({"email": "starlette@example.com"})
        context = MagicMock()
        context.request_headers = None
        context.request = MagicMock()
        context.request.headers = {"Authorization": f"Bearer {token}"}

        email = _extract_email_from_jwt(context)
        assert email == "starlette@example.com"


class TestGetOrCreateAgent:
    """Test the _agents cache and cold-start behavior."""

    @patch("agent.runtime_app.create_agent")
    def test_cold_start_creates_agent(self, mock_create):
        from agent.runtime_app import _get_or_create_agent, _agents

        mock_agent = MagicMock()
        mock_agent._session_manager = MagicMock()
        mock_create.return_value = mock_agent

        # Clear cache
        _agents.clear()

        agent = _get_or_create_agent("user@test.com", "sess-1")
        assert agent == mock_agent
        mock_create.assert_called_once_with(email="user@test.com", session_id="sess-1", user_message=None)

    @patch("agent.runtime_app.create_agent")
    def test_cache_hit_returns_same_agent(self, mock_create):
        from agent.runtime_app import _get_or_create_agent, _agents

        mock_agent = MagicMock()
        mock_agent._session_manager = MagicMock()
        mock_create.return_value = mock_agent

        _agents.clear()

        agent1 = _get_or_create_agent("user@test.com", "sess-1")
        agent2 = _get_or_create_agent("user@test.com", "sess-1")

        assert agent1 is agent2
        assert mock_create.call_count == 1  # Only called once

    @patch("agent.runtime_app.create_agent")
    def test_different_sessions_get_different_agents(self, mock_create):
        from agent.runtime_app import _get_or_create_agent, _agents

        mock_create.side_effect = [MagicMock(_session_manager=MagicMock()), MagicMock(_session_manager=MagicMock())]
        _agents.clear()

        agent1 = _get_or_create_agent("user@test.com", "sess-1")
        agent2 = _get_or_create_agent("user@test.com", "sess-2")

        assert agent1 is not agent2
        assert mock_create.call_count == 2

    @patch("agent.runtime_app.create_agent")
    def test_different_users_same_session_id_isolated(self, mock_create):
        """Even with same session_id, different users get separate agents."""
        from agent.runtime_app import _get_or_create_agent, _agents

        mock_create.side_effect = [MagicMock(_session_manager=MagicMock()), MagicMock(_session_manager=MagicMock())]
        _agents.clear()

        agent_alice = _get_or_create_agent("alice@test.com", "shared-id")
        agent_bob = _get_or_create_agent("bob@test.com", "shared-id")

        assert agent_alice is not agent_bob
        assert mock_create.call_count == 2

    @patch("agent.runtime_app._load_history")
    @patch("agent.runtime_app._inject_history")
    @patch("agent.runtime_app.create_agent")
    def test_no_session_manager_loads_from_ddb(self, mock_create, mock_inject, mock_load):
        """Without session_manager, falls back to DDB history loading."""
        from agent.runtime_app import _get_or_create_agent, _agents

        mock_agent = MagicMock()
        mock_agent._session_manager = None
        mock_create.return_value = mock_agent
        mock_load.return_value = [{"role": "user", "content": "hello"}]
        _agents.clear()

        _get_or_create_agent("user@test.com", "sess-fallback")

        mock_load.assert_called_once_with("sess-fallback")
        mock_inject.assert_called_once()

    @patch("agent.runtime_app.create_agent")
    def test_session_manager_skips_ddb_load(self, mock_create):
        """With session_manager active, no DDB history loading."""
        from agent.runtime_app import _get_or_create_agent, _agents

        mock_agent = MagicMock()
        mock_agent._session_manager = MagicMock()
        mock_create.return_value = mock_agent
        _agents.clear()

        with patch("agent.runtime_app._load_history") as mock_load:
            _get_or_create_agent("user@test.com", "sess-memory")
            mock_load.assert_not_called()


class TestSessionPinningE2E:
    """End-to-end tests for the session pinning flow."""

    def test_parse_payload_requires_session_id(self):
        """Missing session_id should raise ValueError."""
        from agent.runtime_app import _parse_payload

        with pytest.raises(ValueError, match="session_id is required"):
            _parse_payload({"email": "a@b.com", "message": "hi"})

    def test_parse_payload_extracts_email_from_jwt(self):
        """When email is not in payload, extract from JWT in context."""
        from agent.runtime_app import _parse_payload

        token = _make_jwt({"email": "jwt-user@example.com"})
        context = MagicMock()
        context.request_headers = {"Authorization": f"Bearer {token}"}

        email, msg, sid, refs, prompt = _parse_payload(
            {"message": "test", "session_id": "s1"}, context
        )
        assert email == "jwt-user@example.com"

    @mock_aws
    def test_full_session_isolation_flow(self):
        """Simulate two users hitting the same session_id — data stays isolated."""
        self._setup_tables()
        from agent.runtime_app import _ensure_session, _save_message

        # Alice creates session and posts a message
        _ensure_session("alice@corp.com", "session-X", "2026-01-01T00:00:00Z")
        _save_message("session-X", "user", "Alice's secret plan", "2026-01-01T00:00:01Z")

        # Bob tries with same session_id — gets separate session record
        _ensure_session("bob@corp.com", "session-X", "2026-01-01T00:00:02Z")

        sessions_table = boto3.resource("dynamodb", region_name="us-east-1").Table("test-sessions")

        # Bob's record exists independently
        bob_item = sessions_table.get_item(Key={"email": "bob@corp.com", "session_id": "session-X"}).get("Item")
        assert bob_item is not None

        # Alice's record untouched
        alice_item = sessions_table.get_item(Key={"email": "alice@corp.com", "session_id": "session-X"}).get("Item")
        assert alice_item is not None
        assert alice_item["created_at"] == "2026-01-01T00:00:00Z"

        # Messages table is keyed by session_id (shared) — this is why
        # AgentCore Memory uses actor_id=email for isolation
        # The DDB messages table is legacy fallback only

    def _setup_tables(self):
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
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "session-id-index",
                    "KeySchema": [{"AttributeName": "session_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
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
