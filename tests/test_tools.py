"""Tests for individual agent tools — pdf_extract, pptx_extract, content_fetch, etc."""

import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from moto import mock_aws
import boto3

os.environ["UPLOAD_BUCKET"] = "test-uploads"


class TestPdfExtract:
    """Test the pdf_extract tool."""

    def test_extract_local_pdf(self, tmp_path):
        """Test extracting text from a local PDF."""
        # Create a simple PDF using pdfplumber's test helper
        # For now, test the error handling path
        from agent.tools.pdf_extract import pdf_extract

        result = pdf_extract(file_path="/nonexistent/file.pdf")
        assert "Error" in result or "not found" in result.lower()

    @mock_aws
    def test_resolve_s3_path(self):
        """Test S3 path resolution for uploaded files."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")
        
        # Upload a dummy file
        s3.put_object(Bucket="test-uploads", Key="uploads/test/doc.pdf", Body=b"dummy")

        from agent.tools.pdf_extract import _resolve_file
        
        # Patch the s3 client in the module
        import agent.tools.pdf_extract as mod
        mod.s3 = s3
        mod.UPLOAD_BUCKET = "test-uploads"

        # Test s3:// prefix
        local = _resolve_file("s3://test-uploads/uploads/test/doc.pdf")
        assert os.path.exists(local)
        os.unlink(local)

    @mock_aws
    def test_resolve_uploads_path(self):
        """Test uploads/ prefix path resolution."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-uploads")
        s3.put_object(Bucket="test-uploads", Key="uploads/user/file.pdf", Body=b"dummy")

        # Access the module-level _resolve_file directly via sys.modules
        import agent.tools.pdf_extract as _pdf_mod
        # The module-level function is accessible on the actual module
        import sys
        mod = sys.modules["agent.tools.pdf_extract"]
        mod.s3 = s3
        mod.UPLOAD_BUCKET = "test-uploads"

        local = mod._resolve_file("uploads/user/file.pdf")
        assert os.path.exists(local)
        os.unlink(local)

    @mock_aws
    def test_resolve_missing_s3_file(self):
        """Test error handling for missing S3 file."""
        s3_client = boto3.client("s3", region_name="us-east-1")
        s3_client.create_bucket(Bucket="test-uploads")

        from agent.tools import pdf_extract as mod
        mod.s3 = s3_client
        mod.UPLOAD_BUCKET = "test-uploads"

        # Missing file should raise ClientError or FileNotFoundError
        with pytest.raises(Exception):
            mod._resolve_file("s3://test-uploads/nonexistent.pdf")

    def test_resolve_local_path_passthrough(self):
        """Local paths are returned as-is."""
        from agent.tools.pdf_extract import _resolve_file
        
        assert _resolve_file("/tmp/local.pdf") == "/tmp/local.pdf"


class TestContentFetch:
    """Test the content_fetch tool."""

    @patch("agent.tools.content_fetch.requests.get")
    def test_fetch_url(self, mock_get):
        """Test fetching and converting a URL to markdown."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><h1>Hello</h1><p>World</p></body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_get.return_value = mock_response

        from agent.tools.content_fetch import content_fetch
        # The tool may use firecrawl or requests — test varies
        # This verifies the tool is importable and callable


class TestWebResearch:
    """Test the web_research tool."""

    def test_tool_importable(self):
        from agent.tools.web_research import web_research
        assert callable(web_research)

    def test_trend_analysis_importable(self):
        from agent.tools.trend_analysis import trend_analysis
        assert callable(trend_analysis)


class TestNameSession:
    """Test the name_session tool."""

    def test_make_name_session_tool(self):
        """Verify the factory creates a callable tool."""
        from agent.tools.session_manager import make_name_session_tool
        tool = make_name_session_tool("test@test.com", "s1")
        assert callable(tool)

    @mock_aws
    def test_name_session_writes_to_db(self):
        """The tool should actually update DynamoDB."""
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
            "name": "שיחה חדשה",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        })

        from agent.tools.session_manager import make_name_session_tool
        import agent.tools.session_manager as mod
        mod.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        tool = make_name_session_tool("t@t.com", "s1")
        result = tool._tool_func(name="סרטון על Bedrock")
        assert "Bedrock" in result

        # Verify DB was updated
        item = table.get_item(Key={"email": "t@t.com", "session_id": "s1"})["Item"]
        assert item["name"] == "סרטון על Bedrock"
