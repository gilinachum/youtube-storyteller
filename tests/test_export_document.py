"""Tests for export_document tool — verifies RFC 5987 Content-Disposition for non-ASCII filenames."""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from urllib.parse import quote

os.environ.setdefault("SESSIONS_TABLE", "test-sessions")
os.environ.setdefault("UPLOAD_BUCKET", "test-uploads")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


class TestExportDocumentContentDisposition:
    """Verify that export_document uses RFC 5987 encoding for non-ASCII filenames."""

    def test_hebrew_filename_encoding(self):
        """Hebrew filename in ContentDisposition is percent-encoded, not raw Unicode."""
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        with patch("agent.tools.export_document.s3", mock_s3), \
             patch("agent.tools.export_document.dynamodb", mock_dynamodb):
            from agent.tools.export_document import make_export_document_tool

            tool_fn = make_export_document_tool(email="t@t.com", session_id="sess-123")
            # Call underlying function (Strands @tool wraps it)
            result = tool_fn._tool_func(
                title="תכנון סרטון בעברית",
                video_type="tutorial",
                duration_estimate="10:00",
                hook="הוק מעולה",
                sections="## חלק 1\nתוכן",
                thumbnail_suggestion="תמונה יפה",
                seo_tags_hebrew="AI, בינה מלאכותית",
                seo_tags_english="AI, agents",
            )

        # Verify s3.put_object was called
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]

        # ContentDisposition must use RFC 5987 encoding
        cd = call_kwargs["ContentDisposition"]
        assert "filename*=UTF-8''" in cd
        # Must NOT contain raw Hebrew
        assert "תכנון" not in cd

    def test_ascii_filename_encoding(self):
        """ASCII filename also uses RFC 5987 format (consistent behavior)."""
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        with patch("agent.tools.export_document.s3", mock_s3), \
             patch("agent.tools.export_document.dynamodb", mock_dynamodb):
            from agent.tools.export_document import make_export_document_tool

            tool_fn = make_export_document_tool(email="t@t.com", session_id="sess-456")
            result = tool_fn._tool_func(
                title="My English Video",
                video_type="review",
                duration_estimate="5:00",
                hook="Great hook",
                sections="## Part 1\nContent",
                thumbnail_suggestion="Nice image",
                seo_tags_hebrew="טכנולוגיה",
                seo_tags_english="tech, review",
            )

        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        cd = call_kwargs["ContentDisposition"]
        assert "filename*=UTF-8''" in cd
        assert "My%20English%20Video" in cd or "My English Video" in cd.split("''")[1]
