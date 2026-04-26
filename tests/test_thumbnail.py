"""Tests for thumbnail generation tools."""

import json
import pytest
from unittest.mock import patch, MagicMock

from agent.tools.list_style_templates import list_style_templates
from agent.tools.list_user_photos import make_list_user_photos_tool, _get_user_photos, _save_user_photos


class TestListStyleTemplates:
    """Tests for list_style_templates tool."""

    @patch("agent.tools.list_style_templates._s3")
    def test_returns_templates_from_s3(self, mock_s3):
        templates = [
            {"id": "bold_bright", "name": "Bold & Bright", "description": "High contrast", "style_notes": "Vivid colors"},
            {"id": "minimal", "name": "Minimal Clean", "description": "Simple", "style_notes": "White space"},
        ]
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=json.dumps(templates).encode("utf-8")))
        }

        result = json.loads(list_style_templates._tool_func())
        assert len(result) == 2
        assert result[0]["s3_key"] == "templates/thumbnails/bold_bright.png"
        assert result[1]["name"] == "Minimal Clean"

    @patch("agent.tools.list_style_templates._s3")
    def test_returns_empty_on_no_manifest(self, mock_s3):
        mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_s3.get_object.side_effect = mock_s3.exceptions.NoSuchKey()

        result = json.loads(list_style_templates._tool_func())
        assert result == []

    @patch("agent.tools.list_style_templates._s3")
    def test_returns_empty_on_error(self, mock_s3):
        mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_s3.get_object.side_effect = RuntimeError("S3 error")

        result = json.loads(list_style_templates._tool_func())
        assert result == []


class TestListUserPhotos:
    """Tests for list_user_photos tool."""

    @patch("agent.tools.list_user_photos._s3")
    def test_returns_photos_for_user(self, mock_s3):
        photos = [
            {"file_id": "abc123", "filename": "headshot.jpg", "description": "Professional headshot, smiling"},
        ]
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=json.dumps(photos).encode("utf-8")))
        }

        tool_fn = make_list_user_photos_tool("test@example.com")
        result = json.loads(tool_fn._tool_func())
        assert result["count"] == 1
        assert result["photos"][0]["file_id"] == "abc123"

    @patch("agent.tools.list_user_photos._s3")
    def test_returns_empty_for_new_user(self, mock_s3):
        mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_s3.get_object.side_effect = mock_s3.exceptions.NoSuchKey()

        tool_fn = make_list_user_photos_tool("new@example.com")
        result = json.loads(tool_fn._tool_func())
        assert result["photos"] == []
        assert "message" in result


class TestGenerateThumbnail:
    """Tests for generate_thumbnail tool."""

    @patch("agent.tools.generate_thumbnail._get_gemini_client")
    @patch("agent.tools.generate_thumbnail._s3")
    def test_successful_generation(self, mock_s3, mock_get_client):
        from agent.tools.generate_thumbnail import make_generate_thumbnail_tool

        generate_thumbnail = make_generate_thumbnail_tool("test@example.com")

        # Mock Gemini response
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_part_image = MagicMock()
        mock_part_image.inline_data = MagicMock()
        mock_part_image.inline_data.data = b"\x89PNG fake image data"
        mock_part_image.text = None

        mock_part_text = MagicMock()
        mock_part_text.inline_data = None
        mock_part_text.text = "Here's your thumbnail"

        mock_response = MagicMock()
        mock_response.candidates = [
            MagicMock(content=MagicMock(parts=[mock_part_image, mock_part_text]))
        ]
        mock_client.models.generate_content.return_value = mock_response

        # Mock S3
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/thumb.png"

        raw_result = generate_thumbnail._tool_func(
            prompt="Bold text '5 AWS Tips', blue gradient background",
            session_id="test-session",
        )

        # Result starts with markdown image, then JSON
        assert raw_result.startswith("![thumbnail](")
        json_part = raw_result.split("\n\n", 1)[1]
        result = json.loads(json_part)
        assert result["success"] is True
        assert "url" in result
        assert "s3_key" in result
        mock_s3.put_object.assert_called_once()

    @patch("agent.tools.generate_thumbnail._get_gemini_client")
    def test_handles_no_image_response(self, mock_get_client):
        from agent.tools.generate_thumbnail import make_generate_thumbnail_tool

        generate_thumbnail = make_generate_thumbnail_tool("test@example.com")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_part = MagicMock()
        mock_part.inline_data = None
        mock_part.text = "I cannot generate that image"

        mock_response = MagicMock()
        mock_response.candidates = [
            MagicMock(content=MagicMock(parts=[mock_part]))
        ]
        mock_client.models.generate_content.return_value = mock_response

        result = json.loads(generate_thumbnail._tool_func(
            prompt="test prompt",
        ))

        assert result["success"] is False
        assert "No image generated" in result["error"]

    @patch("agent.tools.generate_thumbnail._get_gemini_client")
    def test_handles_api_error(self, mock_get_client):
        from agent.tools.generate_thumbnail import make_generate_thumbnail_tool

        generate_thumbnail = make_generate_thumbnail_tool("test@example.com")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content.side_effect = RuntimeError("API quota exceeded")

        result = json.loads(generate_thumbnail._tool_func(
            prompt="test prompt",
        ))

        assert result["success"] is False
        assert "API quota exceeded" in result["error"]
