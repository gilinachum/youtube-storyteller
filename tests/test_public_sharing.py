"""Tests for public session sharing — visibility, unshare, access control."""

import os
import json
import pytest
from moto import mock_aws
import boto3

os.environ.setdefault("SESSIONS_TABLE", "test-sessions")
os.environ.setdefault("MESSAGES_TABLE", "test-messages")
os.environ.setdefault("UPLOAD_BUCKET", "test-uploads")
# NOTE: do NOT set AGENTCORE_MEMORY_ID here. This file doesn't exercise memory
# behavior, so it has no need to force it empty — and doing so with unconditional
# `os.environ[...] =` (not setdefault, no fixture teardown) permanently clobbers
# the var for the rest of the pytest session, breaking test_long_term_memory.py's
# tests that need AGENTCORE_MEMORY_ID set to a real value. If a test in this file
# ever needs it empty, use `with patch.dict(os.environ, {"AGENTCORE_MEMORY_ID": ""}):`
# scoped to that test instead of a module-level assignment.


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


def _seed_session(table, email="owner@test.com", session_id="sess-001",
                  shared_with=None, visibility=None):
    """Create a session with optional shared_with list and visibility."""
    item = {
        "email": email,
        "session_id": session_id,
        "name": "Test Session",
        "created_at": "2026-05-09T10:00:00Z",
        "updated_at": "2026-05-09T10:00:00Z",
    }
    if shared_with:
        item["shared_with"] = shared_with
    if visibility:
        item["visibility"] = visibility
    table.put_item(Item=item)


def _seed_messages(table, session_id="sess-001"):
    """Add sample messages to a session."""
    table.put_item(Item={
        "session_id": session_id,
        "timestamp": "2026-05-09T10:01:00Z",
        "role": "user",
        "content": "Hello",
    })
    table.put_item(Item={
        "session_id": session_id,
        "timestamp": "2026-05-09T10:01:05Z",
        "role": "assistant",
        "content": "Hi there!",
    })


class TestSetVisibility:
    """Test PATCH /sessions/{id}/visibility endpoint."""

    @mock_aws
    def test_set_visibility_public(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table)

        from api.sessions import handler
        event = _make_event(
            method="PATCH",
            path="/sessions/sess-001/visibility",
            path_params={"id": "sess-001"},
            body={"visibility": "public"},
            email="owner@test.com",
        )
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert body["visibility"] == "public"

        # Verify DDB
        item = table.get_item(Key={"email": "owner@test.com", "session_id": "sess-001"})["Item"]
        assert item["visibility"] == "public"

    @mock_aws
    def test_set_visibility_private(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table, visibility="public")

        from api.sessions import handler
        event = _make_event(
            method="PATCH",
            path="/sessions/sess-001/visibility",
            path_params={"id": "sess-001"},
            body={"visibility": "private"},
            email="owner@test.com",
        )
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert body["visibility"] == "private"

        item = table.get_item(Key={"email": "owner@test.com", "session_id": "sess-001"})["Item"]
        assert item["visibility"] == "private"

    @mock_aws
    def test_set_visibility_non_owner_rejected(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table, shared_with=["friend@test.com"])

        from api.sessions import handler
        event = _make_event(
            method="PATCH",
            path="/sessions/sess-001/visibility",
            path_params={"id": "sess-001"},
            body={"visibility": "public"},
            email="friend@test.com",
        )
        resp = handler(event, None)
        assert resp["statusCode"] == 403


class TestPublicAccess:
    """Test public session access control."""

    @mock_aws
    def test_public_session_viewable_by_any_user(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        sess_table = ddb.Table("test-sessions")
        msgs_table = ddb.Table("test-messages")
        _seed_session(sess_table, visibility="public")
        _seed_messages(msgs_table)

        from api.sessions import handler
        event = _make_event(
            method="GET",
            path="/sessions/sess-001",
            path_params={"id": "sess-001"},
            email="stranger@test.com",
        )
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert len(body["messages"]) == 2

    @mock_aws
    def test_private_session_not_viewable_by_stranger(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table)  # default is private (no visibility attr)

        from api.sessions import handler
        event = _make_event(
            method="GET",
            path="/sessions/sess-001",
            path_params={"id": "sess-001"},
            email="stranger@test.com",
        )
        resp = handler(event, None)
        assert resp["statusCode"] == 403

    @mock_aws
    def test_public_session_returns_viewer_access(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        sess_table = ddb.Table("test-sessions")
        msgs_table = ddb.Table("test-messages")
        _seed_session(sess_table, visibility="public")
        _seed_messages(msgs_table)

        from api.sessions import handler
        event = _make_event(
            method="GET",
            path="/sessions/sess-001",
            path_params={"id": "sess-001"},
            email="viewer@test.com",
        )
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert body["access"] == "viewer"

    @mock_aws
    def test_owner_gets_owner_access(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        sess_table = ddb.Table("test-sessions")
        msgs_table = ddb.Table("test-messages")
        _seed_session(sess_table, visibility="public")
        _seed_messages(msgs_table)

        from api.sessions import handler
        event = _make_event(
            method="GET",
            path="/sessions/sess-001",
            path_params={"id": "sess-001"},
            email="owner@test.com",
        )
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert body["access"] == "owner"

    @mock_aws
    def test_collaborator_gets_collaborator_access(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        sess_table = ddb.Table("test-sessions")
        msgs_table = ddb.Table("test-messages")
        _seed_session(sess_table, shared_with=["collab@test.com"])
        _seed_messages(msgs_table)

        from api.sessions import handler
        event = _make_event(
            method="GET",
            path="/sessions/sess-001",
            path_params={"id": "sess-001"},
            email="collab@test.com",
        )
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert body["access"] == "collaborator"

    @mock_aws
    def test_public_session_not_in_stranger_list(self):
        """Public sessions should NOT appear in other users' /sessions list."""
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table, visibility="public")

        from api.sessions import handler
        event = _make_event(method="GET", path="/sessions", email="stranger@test.com")
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert len(body["sessions"]) == 0

    @mock_aws
    def test_visibility_default_is_private(self):
        """Sessions without visibility attribute should be treated as private."""
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table)  # No visibility attr

        from api.sessions import handler
        # Stranger cannot access
        event = _make_event(
            method="GET",
            path="/sessions/sess-001",
            path_params={"id": "sess-001"},
            email="stranger@test.com",
        )
        resp = handler(event, None)
        assert resp["statusCode"] == 403

        # Owner gets it with default visibility
        event2 = _make_event(
            method="GET",
            path="/sessions/sess-001",
            path_params={"id": "sess-001"},
            email="owner@test.com",
        )
        resp2 = handler(event2, None)
        body2 = json.loads(resp2["body"])
        assert body2["visibility"] == "private"


class TestUnshareSession:
    """Test DELETE /sessions/{id}/share/{email} endpoint."""

    @mock_aws
    def test_unshare_session(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table, shared_with=["friend@test.com", "other@test.com"])

        from api.sessions import handler
        event = _make_event(
            method="DELETE",
            path="/sessions/sess-001/share/friend@test.com",
            path_params={"id": "sess-001"},
            email="owner@test.com",
        )
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert body["removed"] == "friend@test.com"

        # Verify DDB
        item = table.get_item(Key={"email": "owner@test.com", "session_id": "sess-001"})["Item"]
        assert "friend@test.com" not in item["shared_with"]
        assert "other@test.com" in item["shared_with"]

    @mock_aws
    def test_unshare_nonexistent_email(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table, shared_with=["friend@test.com"])

        from api.sessions import handler
        event = _make_event(
            method="DELETE",
            path="/sessions/sess-001/share/nobody@test.com",
            path_params={"id": "sess-001"},
            email="owner@test.com",
        )
        resp = handler(event, None)
        body = json.loads(resp["body"])

        assert resp["statusCode"] == 200
        assert body["message"] == "Not shared with this email"

    @mock_aws
    def test_unshare_non_owner_rejected(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        _seed_session(table, shared_with=["friend@test.com"])

        from api.sessions import handler
        event = _make_event(
            method="DELETE",
            path="/sessions/sess-001/share/friend@test.com",
            path_params={"id": "sess-001"},
            email="friend@test.com",  # Not the owner
        )
        resp = handler(event, None)
        assert resp["statusCode"] == 403


class TestDownloadFileAccess:
    """Test that file downloads enforce access control."""

    @mock_aws
    def test_owner_can_download_file(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        table.put_item(Item={
            "email": "owner@test.com",
            "session_id": "sess-001",
            "files": [{"file_id": "f1", "filename": "test.pdf", "s3_key": "uploads/test.pdf"}],
        })
        # S3 mock bucket
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")

        from api.sessions import handler
        event = _make_event(
            method="GET",
            path="/sessions/sess-001/files/f1",
            path_params={"id": "sess-001"},
            email="owner@test.com",
        )
        resp = handler(event, None)
        assert resp["statusCode"] == 200
        assert "download_url" in json.loads(resp["body"])

    @mock_aws
    def test_collaborator_can_download_file(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        table.put_item(Item={
            "email": "owner@test.com",
            "session_id": "sess-001",
            "shared_with": ["friend@test.com"],
            "files": [{"file_id": "f1", "filename": "test.pdf", "s3_key": "uploads/test.pdf"}],
        })
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")

        from api.sessions import handler
        event = _make_event(
            method="GET",
            path="/sessions/sess-001/files/f1",
            path_params={"id": "sess-001"},
            email="friend@test.com",
        )
        resp = handler(event, None)
        assert resp["statusCode"] == 200

    @mock_aws
    def test_viewer_can_download_file_from_public_session(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        table.put_item(Item={
            "email": "owner@test.com",
            "session_id": "sess-001",
            "visibility": "public",
            "files": [{"file_id": "f1", "filename": "test.pdf", "s3_key": "uploads/test.pdf"}],
        })
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")

        from api.sessions import handler
        event = _make_event(
            method="GET",
            path="/sessions/sess-001/files/f1",
            path_params={"id": "sess-001"},
            email="stranger@test.com",
        )
        resp = handler(event, None)
        assert resp["statusCode"] == 200

    @mock_aws
    def test_stranger_cannot_download_from_private_session(self):
        _create_tables()
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-sessions")
        table.put_item(Item={
            "email": "owner@test.com",
            "session_id": "sess-001",
            "visibility": "private",
            "files": [{"file_id": "f1", "filename": "test.pdf", "s3_key": "uploads/test.pdf"}],
        })

        from api.sessions import handler
        event = _make_event(
            method="GET",
            path="/sessions/sess-001/files/f1",
            path_params={"id": "sess-001"},
            email="stranger@test.com",
        )
        resp = handler(event, None)
        assert resp["statusCode"] == 403
