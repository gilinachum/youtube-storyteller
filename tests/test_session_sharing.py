"""Tests for session sharing — share, dedup, read access, write isolation.

Covers the fix for duplicate share prevention (read-then-write pattern)
and verifies shared session access for both owner and recipient.
"""

import os
import json
import pytest
from moto import mock_aws
import boto3

os.environ["SESSIONS_TABLE"] = "test-sessions"
os.environ["MESSAGES_TABLE"] = "test-messages"
os.environ["UPLOAD_BUCKET"] = "test-uploads"
os.environ["AGENTCORE_MEMORY_ID"] = ""  # Disable memory reads for unit tests


def _make_event(method="GET", path="/", body=None, path_params=None, email="owner@test.com"):
    """Build an API Gateway proxy event with Cognito claims."""
    return {
        "httpMethod": method,
        "path": path,
        "body": json.dumps(body) if body else None,
        "queryStringParameters": {},
        "pathParameters": path_params or {},
        "headers": {"Content-Type": "application/json"},
        "requestContext": {
            "authorizer": {
                "claims": {"email": email},
            },
        },
    }


def _create_tables():
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


def _seed_session(table, email="owner@test.com", session_id="sess-001", shared_with=None):
    """Create a session with optional shared_with list."""
    item = {
        "email": email,
        "session_id": session_id,
        "name": "Test Session",
        "created_at": "2026-05-06T10:00:00Z",
        "updated_at": "2026-05-06T10:00:00Z",
    }
    if shared_with:
        item["shared_with"] = shared_with
    table.put_item(Item=item)


def _seed_messages(table, session_id="sess-001"):
    """Add sample messages to a session."""
    table.put_item(Item={
        "session_id": session_id,
        "timestamp": "2026-05-06T10:01:00Z",
        "role": "user",
        "content": "Hello from owner",
        "sender_email": "owner@test.com",
    })
    table.put_item(Item={
        "session_id": session_id,
        "timestamp": "2026-05-06T10:01:05Z",
        "role": "assistant",
        "content": "Hello! How can I help?",
    })
    table.put_item(Item={
        "session_id": session_id,
        "timestamp": "2026-05-06T10:02:00Z",
        "role": "user",
        "content": "Hello from shared user",
        "sender_email": "friend@test.com",
    })


class TestShareSession:
    """Test POST /sessions/{id}/share endpoint."""

    @mock_aws
    def test_share_session_success(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table)

        from api.sessions import handler
        event = _make_event(
            method="POST",
            path="/sessions/sess-001/share",
            path_params={"id": "sess-001"},
            body={"share_with": "friend@test.com"},
            email="owner@test.com",
        )
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert body["message"] == "Session shared"
        assert body["shared_with"] == "friend@test.com"

        # Verify DDB
        item = table.get_item(Key={"email": "owner@test.com", "session_id": "sess-001"})["Item"]
        assert "friend@test.com" in item["shared_with"]

    @mock_aws
    def test_share_duplicate_prevention(self):
        """Sharing the same email twice should NOT create duplicates."""
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table, shared_with=["friend@test.com"])

        from api.sessions import handler
        event = _make_event(
            method="POST",
            path="/sessions/sess-001/share",
            path_params={"id": "sess-001"},
            body={"share_with": "friend@test.com"},
            email="owner@test.com",
        )
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert body["message"] == "Already shared"

        # Verify no duplicates in DDB
        item = table.get_item(Key={"email": "owner@test.com", "session_id": "sess-001"})["Item"]
        assert item["shared_with"].count("friend@test.com") == 1

    @mock_aws
    def test_share_multiple_users(self):
        """Can share with multiple different users."""
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table)

        from api.sessions import handler

        # Share with first user
        event1 = _make_event(
            method="POST", path="/sessions/sess-001/share",
            path_params={"id": "sess-001"},
            body={"share_with": "user1@test.com"}, email="owner@test.com",
        )
        handler(event1, None)

        # Share with second user
        event2 = _make_event(
            method="POST", path="/sessions/sess-001/share",
            path_params={"id": "sess-001"},
            body={"share_with": "user2@test.com"}, email="owner@test.com",
        )
        handler(event2, None)

        item = table.get_item(Key={"email": "owner@test.com", "session_id": "sess-001"})["Item"]
        assert set(item["shared_with"]) == {"user1@test.com", "user2@test.com"}

    @mock_aws
    def test_share_with_self_rejected(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table)

        from api.sessions import handler
        event = _make_event(
            method="POST", path="/sessions/sess-001/share",
            path_params={"id": "sess-001"},
            body={"share_with": "owner@test.com"}, email="owner@test.com",
        )
        resp = handler(event, None)
        assert resp["statusCode"] == 400
        assert "Cannot share with yourself" in json.loads(resp["body"])["error"]

    @mock_aws
    def test_share_nonexistent_session(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.Table("test-sessions")

        from api.sessions import handler
        event = _make_event(
            method="POST", path="/sessions/no-such-session/share",
            path_params={"id": "no-such-session"},
            body={"share_with": "friend@test.com"}, email="owner@test.com",
        )
        resp = handler(event, None)
        assert resp["statusCode"] == 404

    @mock_aws
    def test_share_missing_email(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table)

        from api.sessions import handler
        event = _make_event(
            method="POST", path="/sessions/sess-001/share",
            path_params={"id": "sess-001"},
            body={"share_with": ""}, email="owner@test.com",
        )
        resp = handler(event, None)
        assert resp["statusCode"] == 400

    @mock_aws
    def test_share_normalizes_email_case(self):
        """Email should be lowercased before storing."""
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table)

        from api.sessions import handler
        event = _make_event(
            method="POST", path="/sessions/sess-001/share",
            path_params={"id": "sess-001"},
            body={"share_with": "Friend@Test.COM"}, email="owner@test.com",
        )
        resp = handler(event, None)
        body = json.loads(resp["body"])
        assert body["shared_with"] == "friend@test.com"

        item = table.get_item(Key={"email": "owner@test.com", "session_id": "sess-001"})["Item"]
        assert "friend@test.com" in item["shared_with"]


class TestSharedSessionAccess:
    """Test that shared users can list and read shared sessions."""

    @mock_aws
    def test_shared_user_sees_session_in_list(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table, shared_with=["friend@test.com"])

        from api.sessions import handler
        event = _make_event(method="GET", path="/sessions", email="friend@test.com")
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        shared = [s for s in body["sessions"] if s.get("_shared")]
        assert len(shared) == 1
        assert shared[0]["session_id"] == "sess-001"
        assert shared[0]["_shared_by"] == "owner@test.com"

    @mock_aws
    def test_shared_user_reads_messages(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        sess_table = ddb.Table("test-sessions")
        msgs_table = ddb.Table("test-messages")
        _seed_session(sess_table, shared_with=["friend@test.com"])
        _seed_messages(msgs_table)

        from api.sessions import handler
        event = _make_event(
            method="GET", path="/sessions/sess-001",
            path_params={"id": "sess-001"}, email="friend@test.com",
        )
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert len(body["messages"]) == 3
        assert body["shared_with"] == ["friend@test.com"]

    @mock_aws
    def test_unshared_user_cannot_see_session(self):
        """A user NOT in shared_with should not see the session in their list."""
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table, shared_with=["friend@test.com"])

        from api.sessions import handler
        event = _make_event(method="GET", path="/sessions", email="stranger@test.com")
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert len(body["sessions"]) == 0

    @mock_aws
    def test_shared_user_cannot_delete_session(self):
        """Shared users should NOT be able to delete the owner's session."""
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table, shared_with=["friend@test.com"])

        from api.sessions import handler
        event = _make_event(
            method="DELETE", path="/sessions/sess-001",
            path_params={"id": "sess-001"}, email="friend@test.com",
        )
        resp = handler(event, None)
        assert resp["statusCode"] == 404

        # Session still exists for owner
        item = table.get_item(Key={"email": "owner@test.com", "session_id": "sess-001"})
        assert item.get("Item") is not None

    @mock_aws
    def test_owner_still_sees_own_session(self):
        """Owner should see their session normally, not as shared."""
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table, shared_with=["friend@test.com"])

        from api.sessions import handler
        event = _make_event(method="GET", path="/sessions", email="owner@test.com")
        resp = handler(event, None)
        body = json.loads(resp["body"])

        own = [s for s in body["sessions"] if not s.get("_shared")]
        assert len(own) == 1
        assert own[0]["session_id"] == "sess-001"


class TestShareIdempotency:
    """Regression tests for the duplicate share bug fix."""

    @mock_aws
    def test_rapid_double_share_no_duplicates(self):
        """Simulate rapid double-share (race condition scenario)."""
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table)

        from api.sessions import handler

        event = _make_event(
            method="POST", path="/sessions/sess-001/share",
            path_params={"id": "sess-001"},
            body={"share_with": "friend@test.com"}, email="owner@test.com",
        )

        # Call share twice
        resp1 = handler(event, None)
        resp2 = handler(event, None)

        assert resp1["statusCode"] == 200
        assert resp2["statusCode"] == 200
        assert json.loads(resp2["body"])["message"] == "Already shared"

        # Verify exactly one entry
        item = table.get_item(Key={"email": "owner@test.com", "session_id": "sess-001"})["Item"]
        assert item["shared_with"].count("friend@test.com") == 1

    @mock_aws
    def test_share_then_share_different_user(self):
        """Share with A, then share with B — both should be present, no dupes."""
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table)

        from api.sessions import handler

        for email in ["a@test.com", "b@test.com", "a@test.com", "b@test.com"]:
            event = _make_event(
                method="POST", path="/sessions/sess-001/share",
                path_params={"id": "sess-001"},
                body={"share_with": email}, email="owner@test.com",
            )
            handler(event, None)

        item = table.get_item(Key={"email": "owner@test.com", "session_id": "sess-001"})["Item"]
        assert sorted(item["shared_with"]) == ["a@test.com", "b@test.com"]
