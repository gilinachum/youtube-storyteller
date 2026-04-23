"""Shared test fixtures for StoryTeller tests."""

import os
import sys
import json
import pytest
import boto3
from moto import mock_aws
from unittest.mock import MagicMock, patch

# Add project root to path so 'agent' and 'api' packages are importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Force test env vars before any module imports
os.environ.setdefault("MESSAGES_TABLE", "test-messages")
os.environ.setdefault("SESSIONS_TABLE", "test-sessions")
os.environ.setdefault("UPLOAD_BUCKET", "test-uploads")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")


@pytest.fixture
def aws_credentials():
    """Mock AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def dynamodb_tables(aws_credentials):
    """Create mocked DynamoDB tables."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")

        # Messages table
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

        # Sessions table
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

        yield client


@pytest.fixture
def s3_bucket(aws_credentials):
    """Create mocked S3 uploads bucket."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")
        yield s3


@pytest.fixture
def sample_payload():
    """Standard test payload for agent invocation."""
    return {
        "email": "test@example.com",
        "message": "אני רוצה לעשות סרטון על Bedrock",
        "session_id": "test-session-001",
    }


@pytest.fixture
def sample_payload_with_files():
    """Test payload with file references."""
    return {
        "email": "test@example.com",
        "message": "תנתח את הקובץ",
        "session_id": "test-session-002",
        "file_refs": [
            {"filename": "slides.pdf", "s3_key": "uploads/test/slides.pdf"},
        ],
    }
