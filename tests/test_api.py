"""Tests for the Lambda API handlers — auth, sessions, upload."""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from moto import mock_aws
import boto3

os.environ["SESSIONS_TABLE"] = "test-sessions"
os.environ["MESSAGES_TABLE"] = "test-messages"
os.environ["UPLOAD_BUCKET"] = "test-uploads"
os.environ["AWS_ACCOUNT_ID"] = "123456789012"


def _make_apigw_event(method="POST", path="/", body=None, query=None, path_params=None):
    """Build a minimal API Gateway proxy event."""
    return {
        "httpMethod": method,
        "path": path,
        "body": json.dumps(body) if body else None,
        "queryStringParameters": query or {},
        "pathParameters": path_params or {},
        "headers": {"Content-Type": "application/json"},
        "requestContext": {},
    }


class TestAuthHandler:
    """Test the auth Lambda."""

    @mock_aws
    def test_verify_valid_email(self):
        # Create sessions table (auth handler checks if table exists)
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

        from api.auth import handler
        event = _make_apigw_event(body={"email": "test@example.com"})
        
        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions"}):
            response = handler(event, {})
        
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "token" in body
        assert body["email"] == "test@example.com"

    def test_verify_missing_email(self):
        from api.auth import handler
        event = _make_apigw_event(body={})
        response = handler(event, {})
        assert response["statusCode"] == 400

    def test_verify_invalid_email(self):
        from api.auth import handler
        # Empty email should be rejected
        event = _make_apigw_event(body={"email": ""})
        response = handler(event, {})
        assert response["statusCode"] == 400


class TestSessionsHandler:
    """Test the sessions Lambda."""

    @mock_aws
    def test_list_sessions(self):
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

        # Seed a session
        table = boto3.resource("dynamodb", region_name="us-east-1").Table("test-sessions")
        table.put_item(Item={
            "email": "t@t.com",
            "session_id": "s1",
            "name": "Test Session",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        })

        from api.sessions import handler
        event = _make_apigw_event(
            method="GET",
            path="/sessions",
            query={"email": "t@t.com"},
        )

        with patch.dict(os.environ, {"SESSIONS_TABLE": "test-sessions", "MESSAGES_TABLE": "test-messages"}):
            response = handler(event, {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert len(body["sessions"]) == 1
        assert body["sessions"][0]["name"] == "Test Session"


class TestUploadHandler:
    """Test the upload Lambda."""

    @mock_aws
    def test_presigned_url_generation(self):
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")

        # Need to also create the sessions table for file tracking
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

        from api import upload as upload_mod
        upload_mod.s3 = s3
        upload_mod.UPLOAD_BUCKET = "test-uploads"
        upload_mod.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        event = _make_apigw_event(body={
            "email": "t@t.com",
            "session_id": "s1",
            "filename": "test.pdf",
            "content_type": "application/pdf",
        })

        response = upload_mod.handler(event, {})
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "upload_url" in body
        assert "key" in body
