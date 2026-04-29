"""Tests for the Lambda API handlers — sessions, upload.

Handlers expect the caller's email (from query/body, or authorizer context
if an overlay is applied). Missing email → 401.
"""

import os
import json
import pytest
from unittest.mock import patch
from moto import mock_aws
import boto3

os.environ["SESSIONS_TABLE"] = "test-sessions"
os.environ["MESSAGES_TABLE"] = "test-messages"
os.environ["UPLOAD_BUCKET"]  = "test-uploads"
os.environ["AWS_ACCOUNT_ID"] = "123456789012"


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
                "sub":   email.split("@")[0] if email else "",
                "name":  "Test User",
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
            {"AttributeName": "email",      "KeyType": "HASH"},
            {"AttributeName": "session_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "email",      "AttributeType": "S"},
            {"AttributeName": "session_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


class TestSessionsHandler:
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
            "session_id":   "s1",
            "filename":     "test.pdf",
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
