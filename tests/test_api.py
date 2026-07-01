"""Tests for the Lambda API handlers — sessions, upload, jobs_poll, transcribe, thumbnail_proxy.

Handlers expect the caller's email (from query/body, or authorizer context
if an overlay is applied). Missing email → 401.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from moto import mock_aws
import boto3

os.environ["SESSIONS_TABLE"] = "test-sessions"
os.environ["MESSAGES_TABLE"] = "test-messages"
os.environ["UPLOAD_BUCKET"] = "test-uploads"
os.environ["JOBS_TABLE"] = "test-jobs"
os.environ["AWS_ACCOUNT_ID"] = "123456789012"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


def _make_apigw_event(method="POST", path="/", body=None, query=None,
                      path_params=None, email="t@t.com"):
    """Build an API Gateway proxy event.

    Sets `authorizer.email` (works with overlay authorizer) AND puts email
    in body / query (works with the default public-repo handlers).
    """
    base = {
        "httpMethod": method,
        "path": path,
        "body": json.dumps(body) if body else None,
        "queryStringParameters": query or {},
        "pathParameters": path_params or {},
        "headers": {"Content-Type": "application/json"},
        "requestContext": {
            "authorizer": {
                "email": email,
                "sub": email.split("@")[0] if email else "",
                "name": "Test User",
                "principalId": email,
            },
        },
    }
    # For body-based requests, inject email if not already there
    if body is not None and "email" not in body:
        body = {**body, "email": email}
        base["body"] = json.dumps(body)
    # For query-based requests (GET/DELETE), add email query param
    if method in ("GET", "DELETE") and email and "email" not in (query or {}):
        base["queryStringParameters"] = {**(query or {}), "email": email}
    return base


def _create_sessions_table():
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


def _create_messages_table():
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


def _create_jobs_table():
    client = boto3.client("dynamodb", region_name="us-east-1")
    client.create_table(
        TableName="test-jobs",
        KeySchema=[
            {"AttributeName": "session_id", "KeyType": "HASH"},
            {"AttributeName": "job_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "session_id", "AttributeType": "S"},
            {"AttributeName": "job_id", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "status-index",
                "KeySchema": [{"AttributeName": "status", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )


# =============================================================================
# Sessions Handler — List
# =============================================================================

class TestSessionsList:
    @mock_aws
    def test_list_sessions(self):
        _create_sessions_table()
        table = boto3.resource("dynamodb", region_name="us-east-1").Table("test-sessions")
        table.put_item(Item={
            "email": "t@t.com",
            "session_id": "s1",
            "name": "Test Session",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        })

        from api.sessions import handler
        event = _make_apigw_event(method="GET", path="/sessions")

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert len(body["sessions"]) == 1
        assert body["sessions"][0]["name"] == "Test Session"

    def test_list_sessions_unauthenticated(self):
        from api.sessions import handler
        event = _make_apigw_event(method="GET", path="/sessions", email="")
        response = handler(event, {})
        assert response["statusCode"] == 401

    @mock_aws
    def test_list_sessions_empty(self):
        """List sessions for a user with no sessions returns empty list."""
        _create_sessions_table()

        from api.sessions import handler
        event = _make_apigw_event(method="GET", path="/sessions", email="nobody@t.com")

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["sessions"] == []

    @mock_aws
    def test_list_sessions_includes_shared(self):
        """Sessions shared with the user appear in listing."""
        _create_sessions_table()
        table = boto3.resource("dynamodb", region_name="us-east-1").Table("test-sessions")
        table.put_item(Item={
            "email": "owner@t.com",
            "session_id": "shared1",
            "name": "Shared Session",
            "shared_with": ["viewer@t.com"],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        })

        from api.sessions import handler
        event = _make_apigw_event(method="GET", path="/sessions", email="viewer@t.com")

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert len(body["sessions"]) == 1
        assert body["sessions"][0]["_shared"] is True
        assert body["sessions"][0]["_shared_by"] == "owner@t.com"


# =============================================================================
# Sessions Handler — Get Session
# =============================================================================

class TestSessionsGet:
    @mock_aws
    def test_get_session_with_messages(self):
        """Get a session returns messages from DDB fallback."""
        _create_sessions_table()
        _create_messages_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        sess_table = db.Table("test-sessions")
        msgs_table = db.Table("test-messages")

        sess_table.put_item(Item={
            "email": "t@t.com",
            "session_id": "s1",
            "name": "My Session",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        })
        msgs_table.put_item(Item={
            "session_id": "s1",
            "timestamp": "2026-01-01T00:01:00Z",
            "role": "user",
            "content": "Hello",
        })
        msgs_table.put_item(Item={
            "session_id": "s1",
            "timestamp": "2026-01-01T00:02:00Z",
            "role": "assistant",
            "content": "Hi there!",
        })

        from api.sessions import handler
        event = _make_apigw_event(
            method="GET", path="/sessions/s1",
            path_params={"id": "s1"},
        )

        with patch.dict(os.environ, {
            "SESSIONS_TABLE": "test-sessions",
            "MESSAGES_TABLE": "test-messages",
            "AGENTCORE_MEMORY_ID": "",
        }):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["session_id"] == "s1"
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][1]["role"] == "assistant"

    @mock_aws
    def test_get_session_not_found(self):
        """Get a session that doesn't exist returns 404."""
        _create_sessions_table()
        _create_messages_table()

        from api.sessions import handler
        event = _make_apigw_event(
            method="GET", path="/sessions/nonexistent",
            path_params={"id": "nonexistent"},
        )

        with patch.dict(os.environ, {
            "SESSIONS_TABLE": "test-sessions",
            "MESSAGES_TABLE": "test-messages",
            "AGENTCORE_MEMORY_ID": "",
        }):
            response = handler(event, {})

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert "error" in body


# =============================================================================
# Sessions Handler — Delete Session
# =============================================================================

class TestSessionsDelete:
    @mock_aws
    def test_delete_session_success(self):
        """Delete an existing session removes session and messages."""
        _create_sessions_table()
        _create_messages_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        sess_table = db.Table("test-sessions")
        msgs_table = db.Table("test-messages")

        sess_table.put_item(Item={
            "email": "t@t.com",
            "session_id": "s1",
            "name": "Doomed",
        })
        msgs_table.put_item(Item={
            "session_id": "s1",
            "timestamp": "2026-01-01T00:01:00Z",
            "content": "test",
        })

        from api.sessions import handler
        event = _make_apigw_event(
            method="DELETE", path="/sessions/s1",
            path_params={"id": "s1"},
        )

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["message"] == "Session deleted"

        # Verify it's gone
        resp = sess_table.get_item(Key={"email": "t@t.com", "session_id": "s1"})
        assert "Item" not in resp

    @mock_aws
    def test_delete_session_not_found(self):
        """Delete a non-existent session returns 404."""
        _create_sessions_table()
        _create_messages_table()

        from api.sessions import handler
        event = _make_apigw_event(
            method="DELETE", path="/sessions/ghost",
            path_params={"id": "ghost"},
        )

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 404

    @mock_aws
    def test_delete_session_wrong_owner(self):
        """Cannot delete another user's session."""
        _create_sessions_table()
        _create_messages_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        sess_table = db.Table("test-sessions")
        sess_table.put_item(Item={
            "email": "owner@t.com",
            "session_id": "s1",
            "name": "Not yours",
        })

        from api.sessions import handler
        event = _make_apigw_event(
            method="DELETE", path="/sessions/s1",
            path_params={"id": "s1"},
            email="attacker@t.com",
        )

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 404


# =============================================================================
# Sessions Handler — Share Session
# =============================================================================

class TestSessionsShare:
    @mock_aws
    def test_share_session_success(self):
        """Share a session with another user."""
        _create_sessions_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        sess_table = db.Table("test-sessions")
        sess_table.put_item(Item={
            "email": "t@t.com",
            "session_id": "s1",
            "name": "Shareable",
        })

        from api.sessions import handler
        event = _make_apigw_event(
            method="POST", path="/sessions/s1/share",
            path_params={"id": "s1"},
            body={"share_with": "friend@t.com"},
        )

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["shared_with"] == "friend@t.com"

        # Verify DDB updated
        resp = sess_table.get_item(Key={"email": "t@t.com", "session_id": "s1"})
        assert "friend@t.com" in resp["Item"]["shared_with"]

    @mock_aws
    def test_share_session_with_self(self):
        """Cannot share a session with yourself."""
        _create_sessions_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        db.Table("test-sessions").put_item(Item={
            "email": "t@t.com",
            "session_id": "s1",
            "name": "Mine",
        })

        from api.sessions import handler
        event = _make_apigw_event(
            method="POST", path="/sessions/s1/share",
            path_params={"id": "s1"},
            body={"share_with": "t@t.com"},
        )

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 400
        assert "yourself" in json.loads(response["body"])["error"].lower()

    @mock_aws
    def test_share_session_missing_email(self):
        """Share without share_with param returns 400."""
        _create_sessions_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        db.Table("test-sessions").put_item(Item={
            "email": "t@t.com",
            "session_id": "s1",
            "name": "Test",
        })

        from api.sessions import handler
        event = _make_apigw_event(
            method="POST", path="/sessions/s1/share",
            path_params={"id": "s1"},
            body={},
        )

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 400

    @mock_aws
    def test_share_session_not_found(self):
        """Share a non-existent session returns 404."""
        _create_sessions_table()

        from api.sessions import handler
        event = _make_apigw_event(
            method="POST", path="/sessions/ghost/share",
            path_params={"id": "ghost"},
            body={"share_with": "friend@t.com"},
        )

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 404

    @mock_aws
    def test_share_session_idempotent(self):
        """Sharing with someone already shared returns 200 (already shared)."""
        _create_sessions_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        db.Table("test-sessions").put_item(Item={
            "email": "t@t.com",
            "session_id": "s1",
            "name": "Test",
            "shared_with": ["friend@t.com"],
        })

        from api.sessions import handler
        event = _make_apigw_event(
            method="POST", path="/sessions/s1/share",
            path_params={"id": "s1"},
            body={"share_with": "friend@t.com"},
        )

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        assert "already" in json.loads(response["body"])["message"].lower()


# =============================================================================
# Sessions Handler — Download File
# =============================================================================

class TestSessionsDownloadFile:
    @mock_aws
    def test_download_file_success(self):
        """Download a file attached to a session."""
        _create_sessions_table()
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")

        db = boto3.resource("dynamodb", region_name="us-east-1")
        db.Table("test-sessions").put_item(Item={
            "email": "t@t.com",
            "session_id": "s1",
            "name": "With File",
            "files": [{
                "file_id": "f1",
                "filename": "notes.pdf",
                "s3_key": "uploads/t@t.com/s1/f1.pdf",
            }],
        })

        from api.sessions import handler
        event = _make_apigw_event(
            method="GET", path="/sessions/s1/files/f1",
            path_params={"id": "s1"},
        )

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages", "UPLOAD_BUCKET": "test-uploads"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "download_url" in body
        assert body["filename"] == "notes.pdf"

    @mock_aws
    def test_download_file_hebrew_filename(self):
        """Download URL for Hebrew filename uses RFC 5987 encoding (no ISO-8859-1 error)."""
        _create_sessions_table()
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")

        hebrew_name = "\u05dc\u05d1\u05e0\u05d5\u05ea \u05d0\u05d5 \u05dc\u05e7\u05e0\u05d5\u05ea.md"
        db = boto3.resource("dynamodb", region_name="us-east-1")
        db.Table("test-sessions").put_item(Item={
            "email": "t@t.com",
            "session_id": "s1",
            "name": "Hebrew File",
            "files": [{
                "file_id": "f1",
                "filename": hebrew_name,
                "s3_key": "uploads/t@t.com/s1/f1.md",
            }],
        })

        from api.sessions import handler
        event = _make_apigw_event(
            method="GET", path="/sessions/s1/files/f1",
            path_params={"id": "s1"},
        )

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages", "UPLOAD_BUCKET": "test-uploads"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "download_url" in body
        # Presigned URL must use percent-encoded filename (RFC 5987)
        # The URL itself percent-encodes the query value, so check for encoded form
        from urllib.parse import unquote
        decoded_url = unquote(body["download_url"])
        assert "filename*=UTF-8''" in decoded_url
        # Must NOT contain raw Hebrew in the disposition param
        assert f'filename="{hebrew_name}"' not in decoded_url

    @mock_aws
    def test_download_file_not_found(self):
        """Download a file that doesn't exist returns 404."""
        _create_sessions_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        db.Table("test-sessions").put_item(Item={
            "email": "t@t.com",
            "session_id": "s1",
            "name": "No Files",
            "files": [],
        })

        from api.sessions import handler
        event = _make_apigw_event(
            method="GET", path="/sessions/s1/files/missing",
            path_params={"id": "s1"},
        )

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 404


# =============================================================================
# Upload Handler
# =============================================================================

class TestUploadHandler:
    @mock_aws
    def test_presigned_url_generation(self):
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")
        _create_sessions_table()

        from api import upload as upload_mod
        upload_mod.s3 = s3
        upload_mod.UPLOAD_BUCKET = "test-uploads"
        upload_mod.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        event = _make_apigw_event(body={
            "session_id": "s1",
            "filename": "test.pdf",
            "content_type": "application/pdf",
        })

        response = upload_mod.handler(event, {})
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "upload_url" in body
        assert "key" in body

    def test_upload_unauthenticated(self):
        from api import upload as upload_mod
        event = _make_apigw_event(body={"session_id": "s1"}, email="")
        response = upload_mod.handler(event, {})
        assert response["statusCode"] == 401


# =============================================================================
# Jobs Poll Handler
# =============================================================================

class TestJobsPollHandler:
    @mock_aws
    def test_poll_no_jobs(self):
        """Poll returns no pending/unconsumed when no jobs exist."""
        _create_jobs_table()

        from api.jobs_poll import handler
        event = _make_apigw_event(
            method="GET", path="/jobs/poll",
            query={"session_id": "s1"},
        )

        with patch.dict(os.environ, {"JOBS_TABLE": "test-jobs"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["has_pending"] is False
        assert body["has_unconsumed"] is False

    @mock_aws
    def test_poll_with_pending_job(self):
        """Poll detects a pending (started, unconsumed) job."""
        _create_jobs_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        db.Table("test-jobs").put_item(Item={
            "session_id": "s1",
            "job_id": "j1",
            "status": "started",
            "consumed": False,
            "job_type": "transcription",
        })

        from api.jobs_poll import handler
        event = _make_apigw_event(
            method="GET", path="/jobs/poll",
            query={"session_id": "s1"},
        )

        with patch.dict(os.environ, {"JOBS_TABLE": "test-jobs"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["has_pending"] is True
        assert body["has_unconsumed"] is False

    @mock_aws
    def test_poll_with_completed_unconsumed_job(self):
        """Poll detects completed unconsumed jobs."""
        _create_jobs_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        db.Table("test-jobs").put_item(Item={
            "session_id": "s1",
            "job_id": "j1",
            "status": "completed",
            "consumed": False,
            "job_type": "transcription",
        })

        from api.jobs_poll import handler
        event = _make_apigw_event(
            method="GET", path="/jobs/poll",
            query={"session_id": "s1"},
        )

        with patch.dict(os.environ, {"JOBS_TABLE": "test-jobs"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["has_pending"] is False
        assert body["has_unconsumed"] is True

    @mock_aws
    def test_poll_consumed_jobs_excluded(self):
        """Already consumed jobs don't show up."""
        _create_jobs_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        db.Table("test-jobs").put_item(Item={
            "session_id": "s1",
            "job_id": "j1",
            "status": "completed",
            "consumed": True,
            "job_type": "transcription",
        })

        from api.jobs_poll import handler
        event = _make_apigw_event(
            method="GET", path="/jobs/poll",
            query={"session_id": "s1"},
        )

        with patch.dict(os.environ, {"JOBS_TABLE": "test-jobs"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["has_pending"] is False
        assert body["has_unconsumed"] is False

    def test_poll_unauthenticated(self):
        """Poll without auth returns 401."""
        from api.jobs_poll import handler
        event = _make_apigw_event(method="GET", path="/jobs/poll", email="")
        response = handler(event, {})
        assert response["statusCode"] == 401

    def test_poll_missing_session_id(self):
        """Poll without session_id returns 400."""
        from api.jobs_poll import handler
        event = _make_apigw_event(method="GET", path="/jobs/poll", query={})
        response = handler(event, {})
        assert response["statusCode"] == 400


# =============================================================================
# Thumbnail Proxy Handler
# =============================================================================

class TestThumbnailProxyHandler:
    @mock_aws
    def test_thumbnail_redirect(self):
        """Valid thumbnail key returns 302 redirect with presigned URL."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")

        from api import thumbnail_proxy
        thumbnail_proxy.s3 = s3
        thumbnail_proxy.UPLOAD_BUCKET = "test-uploads"

        event = {
            "httpMethod": "GET",
            "queryStringParameters": {"key": "thumbnails/user/session/img.png"},
        }

        response = thumbnail_proxy.handler(event, {})
        assert response["statusCode"] == 302
        assert "Location" in response["headers"]
        assert "test-uploads" in response["headers"]["Location"]

    @mock_aws
    def test_thumbnail_profile_path_allowed(self):
        """Profile paths are also allowed."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")

        from api import thumbnail_proxy
        thumbnail_proxy.s3 = s3
        thumbnail_proxy.UPLOAD_BUCKET = "test-uploads"

        event = {
            "httpMethod": "GET",
            "queryStringParameters": {"key": "profile/user/photo.jpg"},
        }

        response = thumbnail_proxy.handler(event, {})
        assert response["statusCode"] == 302

    def test_thumbnail_missing_key(self):
        """Missing key param returns 400."""
        from api import thumbnail_proxy

        event = {
            "httpMethod": "GET",
            "queryStringParameters": {},
        }

        response = thumbnail_proxy.handler(event, {})
        assert response["statusCode"] == 400

    def test_thumbnail_forbidden_path(self):
        """Non-thumbnail/profile paths are forbidden."""
        from api import thumbnail_proxy

        event = {
            "httpMethod": "GET",
            "queryStringParameters": {"key": "secrets/admin/password.txt"},
        }

        response = thumbnail_proxy.handler(event, {})
        assert response["statusCode"] == 403


# =============================================================================
# Transcribe Handler
# =============================================================================

class TestTranscribeHandler:
    def test_transcribe_unauthenticated(self):
        """Transcribe without auth returns 401."""
        from api.transcribe import handler
        event = _make_apigw_event(method="POST", path="/transcribe", email="")
        response = handler(event, {})
        assert response["statusCode"] == 401

    def test_transcribe_invalid_method(self):
        """GET without job_name returns 400."""
        from api.transcribe import handler
        event = _make_apigw_event(method="GET", path="/transcribe", path_params={})
        response = handler(event, {})
        assert response["statusCode"] == 400

    @mock_aws
    def test_start_transcription_missing_fields(self):
        """Start transcription without required fields returns 400."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")

        from api import transcribe
        transcribe.s3 = s3
        transcribe.UPLOAD_BUCKET = "test-uploads"

        event = _make_apigw_event(
            method="POST", path="/transcribe",
            body={"session_id": "s1"},  # missing audio
        )
        response = transcribe.handler(event, {})
        assert response["statusCode"] == 400
        assert "required" in json.loads(response["body"])["error"]

    @mock_aws
    def test_start_transcription_success(self):
        """Start transcription with valid data returns job_name."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")

        from api import transcribe
        transcribe.s3 = s3
        transcribe.UPLOAD_BUCKET = "test-uploads"

        import base64
        audio_b64 = base64.b64encode(b"fake audio data").decode()

        event = _make_apigw_event(
            method="POST", path="/transcribe",
            body={"session_id": "s1", "audio": audio_b64},
        )

        response = transcribe.handler(event, {})
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "job_name" in body
        assert body["status"] == "IN_PROGRESS"
        assert body["job_name"].startswith("storyteller-")

    @mock_aws
    def test_poll_transcription_not_found(self):
        """Poll a non-existent job returns 404."""
        from api import transcribe
        transcribe.transcribe_client = boto3.client("transcribe", region_name="us-east-1")

        event = _make_apigw_event(
            method="GET", path="/transcribe/nonexistent-job",
            path_params={"job_name": "nonexistent-job"},
        )

        response = transcribe.handler(event, {})
        assert response["statusCode"] == 404


# =============================================================================
# Job Resolver Handler
# =============================================================================

class TestJobResolverHandler:
    @mock_aws
    def test_resolver_no_jobs(self):
        """Resolver with no started jobs dispatches nothing."""
        _create_jobs_table()

        from api.job_resolver import handler
        with patch.dict(os.environ, {"JOBS_TABLE": "test-jobs"}):
            # Reimport to pick up the env var
            import importlib
            import api.job_resolver as jr
            importlib.reload(jr)
            jr.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

            result = jr.handler({}, {})

        assert result["dispatched"] == 0

    @mock_aws
    def test_resolver_dispatches_started_jobs(self):
        """Resolver invokes handler Lambda for started jobs."""
        _create_jobs_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        db.Table("test-jobs").put_item(Item={
            "session_id": "s1",
            "job_id": "j1",
            "status": "started",
            "consumed": False,
            "job_type": "transcription",
            "email": "t@t.com",
            "metadata": {},
        })

        import importlib
        import api.job_resolver as jr
        importlib.reload(jr)

        with patch.dict(os.environ, {"JOBS_TABLE": "test-jobs"}):
            jr.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
            mock_lambda = MagicMock()
            jr.lambda_client = mock_lambda

            result = jr.handler({}, {})

        assert result["dispatched"] == 1
        mock_lambda.invoke.assert_called_once()
        call_kwargs = mock_lambda.invoke.call_args[1]
        assert call_kwargs["InvocationType"] == "Event"
        payload = json.loads(call_kwargs["Payload"])
        assert payload["job_id"] == "j1"
        assert payload["job_type"] == "transcription"

    @mock_aws
    def test_resolver_skips_unknown_job_type(self):
        """Resolver skips jobs with unregistered types."""
        _create_jobs_table()

        db = boto3.resource("dynamodb", region_name="us-east-1")
        db.Table("test-jobs").put_item(Item={
            "session_id": "s1",
            "job_id": "j1",
            "status": "started",
            "consumed": False,
            "job_type": "unknown_type",
            "email": "t@t.com",
        })

        import importlib
        import api.job_resolver as jr
        importlib.reload(jr)

        with patch.dict(os.environ, {"JOBS_TABLE": "test-jobs"}):
            jr.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
            mock_lambda = MagicMock()
            jr.lambda_client = mock_lambda

            result = jr.handler({}, {})

        assert result["dispatched"] == 0
        mock_lambda.invoke.assert_not_called()
