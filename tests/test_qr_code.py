"""Unit tests for the QR code generation tool."""
import base64
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

# Import the sanitize function and tool factory
from agent.tools.generate_qr_code import sanitize_url, make_generate_qr_code_tool


# ─── URL Sanitization Tests ──────────────────────────────────────────────────

class TestSanitizeUrl:
    """Test URL validation and sanitization."""

    def test_valid_https_url(self):
        assert sanitize_url("https://example.com") == "https://example.com"

    def test_valid_http_url(self):
        assert sanitize_url("http://example.com/path?q=1") == "http://example.com/path?q=1"

    def test_javascript_scheme_rejected(self):
        assert sanitize_url("javascript:alert(1)") is None

    def test_javascript_scheme_uppercase_rejected(self):
        assert sanitize_url("JavaScript:alert(1)") is None

    def test_data_scheme_rejected(self):
        assert sanitize_url("data:text/html,<h1>hi</h1>") is None

    def test_private_ip_192_168(self):
        assert sanitize_url("http://192.168.1.1/admin") is None

    def test_private_ip_10(self):
        assert sanitize_url("http://10.0.0.1/secret") is None

    def test_private_ip_127(self):
        assert sanitize_url("http://127.0.0.1:8080") is None

    def test_private_ip_169_254(self):
        assert sanitize_url("http://169.254.169.254/latest/meta-data") is None

    def test_empty_url_rejected(self):
        assert sanitize_url("") is None

    def test_url_longer_than_2048_rejected(self):
        long_url = "https://example.com/" + "a" * 2040
        assert sanitize_url(long_url) is None

    def test_whitespace_only_rejected(self):
        assert sanitize_url("   ") is None

    def test_url_with_whitespace_stripped(self):
        assert sanitize_url("  https://example.com  ") == "https://example.com"

    def test_ftp_rejected(self):
        assert sanitize_url("ftp://example.com/file") is None

    def test_no_scheme_rejected(self):
        assert sanitize_url("example.com") is None


# ─── Tool Output Format Tests ────────────────────────────────────────────────

# Fake base64 PNG (1x1 pixel)
FAKE_PNG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50).decode("ascii")


class FakeCodeInterpreter:
    """Mock Code Interpreter that returns pre-canned QR output."""

    def __init__(self, region=None):
        self.started = False
        self.stopped = False
        self._fail = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def execute_code(self, code: str):
        if self._fail:
            raise RuntimeError("CI session crashed")
        # Extract URLs from the code to build a matching response
        import re
        urls_match = re.search(r"urls = (\[.*?\])", code, re.DOTALL)
        urls = eval(urls_match.group(1)) if urls_match else []
        output = [{"url": u, "b64": FAKE_PNG_B64} for u in urls]
        text = "__QR_RESULT__" + json.dumps(output)
        # Return streaming-style response matching Code Interpreter format
        return {
            "stream": [
                {"result": {"content": [{"text": text}]}}
            ]
        }


@pytest.fixture
def mock_ci():
    """Patch CodeInterpreter via sys.modules so the lazy import inside the tool works.

    Restores the previous sys.modules state on teardown — otherwise the fake
    ``bedrock_agentcore`` MagicMock leaks into every other test in the same
    pytest session and breaks real `from bedrock_agentcore.runtime import ...`
    imports elsewhere (e.g. agent/runtime_app.py) with a confusing
    "'bedrock_agentcore' is not a package" error.
    """
    import sys
    fake_module = MagicMock()
    fake_module.CodeInterpreter = FakeCodeInterpreter

    patched_keys = [
        "bedrock_agentcore",
        "bedrock_agentcore.tools",
        "bedrock_agentcore.tools.code_interpreter_client",
    ]
    previous = {key: sys.modules.get(key) for key in patched_keys}

    sys.modules["bedrock_agentcore"] = MagicMock()
    sys.modules["bedrock_agentcore.tools"] = MagicMock()
    sys.modules["bedrock_agentcore.tools.code_interpreter_client"] = fake_module
    try:
        yield fake_module
    finally:
        for key, original in previous.items():
            if original is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = original


@pytest.fixture
def mock_s3():
    """Patch S3 client."""
    with patch("agent.tools.generate_qr_code.s3") as mock:
        mock.put_object = MagicMock(return_value={})
        yield mock


@pytest.fixture
def mock_dynamo():
    """Patch DynamoDB."""
    with patch("agent.tools.generate_qr_code.dynamodb") as mock:
        table = MagicMock()
        mock.Table.return_value = table
        yield mock


class TestToolOutput:
    """Test the tool's output format with mocked dependencies."""

    def test_single_url_generates_media_reference(self, mock_ci, mock_s3, mock_dynamo):
        tool = make_generate_qr_code_tool("test@example.com", "session-123")
        result = tool(urls=["https://example.com"])

        assert "media://" in result
        assert "![QR Code for https://example.com]" in result
        # file_id should be flat (no slashes) — safe for API GW single path segment
        import re
        media_refs = re.findall(r'media://([^)]+)', result)
        assert len(media_refs) == 1
        assert '/' not in media_refs[0], f"file_id must be flat, got: {media_refs[0]}"

    def test_multiple_urls_generate_multiple_references(self, mock_ci, mock_s3, mock_dynamo):
        tool = make_generate_qr_code_tool("test@example.com", "session-123")
        result = tool(urls=["https://a.com", "https://b.com"])

        assert result.count("media://") == 2
        assert "![QR Code for https://a.com]" in result
        assert "![QR Code for https://b.com]" in result

    def test_file_id_is_flat_and_s3_key_has_path(self, mock_ci, mock_s3, mock_dynamo):
        """file_id should be flat filename, s3_key should have the nested path."""
        tool = make_generate_qr_code_tool("test@example.com", "session-123")
        result = tool(urls=["https://example.com"])

        # S3 put_object should use nested key
        call_args = mock_s3.put_object.call_args
        s3_key = call_args[1]["Key"] if "Key" in (call_args[1] or {}) else call_args.kwargs["Key"]
        assert s3_key.startswith("media/qrcodes/test@example.com/session-123/")
        assert s3_key.endswith(".png")

    def test_file_registered_in_dynamo(self, mock_ci, mock_s3, mock_dynamo):
        """Generated files should be registered in session's DDB files array."""
        tool = make_generate_qr_code_tool("test@example.com", "session-123")
        tool(urls=["https://example.com"])

        table = mock_dynamo.Table.return_value
        table.update_item.assert_called_once()
        call_kwargs = table.update_item.call_args[1]
        file_records = call_kwargs["ExpressionAttributeValues"][":files"]
        assert len(file_records) == 1
        rec = file_records[0]
        assert '/' not in rec["file_id"], "file_id must be flat"
        assert rec["s3_key"].startswith("media/qrcodes/"), "s3_key must have nested path"
        assert rec["s3_key"] != rec["file_id"], "s3_key and file_id must differ"

    def test_ci_failure_returns_error(self, mock_s3, mock_dynamo):
        """When Code Interpreter fails to start."""
        import sys
        fake_module = MagicMock()

        def failing_ci(**kwargs):
            raise RuntimeError("Service unavailable")

        fake_module.CodeInterpreter = failing_ci

        patched_keys = ["bedrock_agentcore", "bedrock_agentcore.tools", "bedrock_agentcore.tools.code_interpreter_client"]
        previous = {key: sys.modules.get(key) for key in patched_keys}
        sys.modules["bedrock_agentcore"] = sys.modules.get("bedrock_agentcore") or MagicMock()
        sys.modules["bedrock_agentcore.tools"] = sys.modules.get("bedrock_agentcore.tools") or MagicMock()
        sys.modules["bedrock_agentcore.tools.code_interpreter_client"] = fake_module
        try:
            tool = make_generate_qr_code_tool("test@example.com", "session-123")
            result = tool(urls=["https://example.com"])

            assert "❌" in result
            assert "Code Interpreter" in result or "failed" in result.lower()
        finally:
            for key, original in previous.items():
                if original is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = original

    def test_s3_upload_failure_returns_error(self, mock_ci, mock_dynamo):
        """When S3 upload fails for all URLs."""
        with patch("agent.tools.generate_qr_code.s3") as mock_s3_fail:
            mock_s3_fail.put_object.side_effect = Exception("Access Denied")
            tool = make_generate_qr_code_tool("test@example.com", "session-123")
            result = tool(urls=["https://example.com"])

            assert "❌" in result or "failed" in result.lower() or "S3" in result

    def test_invalid_urls_reported_as_errors(self, mock_ci, mock_s3, mock_dynamo):
        tool = make_generate_qr_code_tool("test@example.com", "session-123")
        result = tool(urls=["javascript:alert(1)", "https://valid.com"])

        # Valid one should succeed
        assert "media://" in result
        assert "![QR Code for https://valid.com]" in result
        # Invalid one should be noted
        assert "javascript:alert(1)" in result

    def test_empty_urls_returns_error(self, mock_ci, mock_s3, mock_dynamo):
        tool = make_generate_qr_code_tool("test@example.com", "session-123")
        result = tool(urls=[])
        assert "❌" in result
