"""Tests for save_user_photo tool."""
import json
from unittest.mock import MagicMock, patch

import pytest


class TestSaveUserPhoto:
    """Tests for make_save_user_photo_tool."""

    @patch("agent.tools.save_user_photo.user_namespace", return_value="testns123")
    @patch("agent.tools.save_user_photo._s3")
    def test_save_photo_success(self, mock_s3, mock_ns):
        from agent.tools.save_user_photo import make_save_user_photo_tool

        save_user_photo = make_save_user_photo_tool("user@example.com")

        # Mock head_object (source exists and is an image)
        mock_s3.head_object.return_value = {"ContentType": "image/jpeg"}
        # Mock copy_object
        mock_s3.copy_object.return_value = {}
        # Mock load manifest (empty)
        mock_s3.exceptions = MagicMock()
        mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_s3.get_object.side_effect = mock_s3.exceptions.NoSuchKey("no key")
        # Mock save manifest
        mock_s3.put_object.return_value = {}

        result = json.loads(save_user_photo._tool_func(
            s3_key="uploads/user@example.com/sess123/abc_photo.jpg",
            filename="photo.jpg",
            description="Person smiling, outdoor setting",
        ))

        assert result["success"] is True
        assert result["total_photos"] == 1
        assert result["photo"]["description"] == "Person smiling, outdoor setting"
        assert result["photo"]["s3_key"].startswith("media/testns123/photos/")

        # Verify copy was called
        mock_s3.copy_object.assert_called_once()
        copy_args = mock_s3.copy_object.call_args
        assert copy_args.kwargs["CopySource"]["Key"] == "uploads/user@example.com/sess123/abc_photo.jpg"

    @patch("agent.tools.save_user_photo.user_namespace", return_value="testns123")
    @patch("agent.tools.save_user_photo._s3")
    def test_reject_non_image(self, mock_s3, mock_ns):
        from agent.tools.save_user_photo import make_save_user_photo_tool

        save_user_photo = make_save_user_photo_tool("user@example.com")

        mock_s3.head_object.return_value = {"ContentType": "application/pdf"}

        result = json.loads(save_user_photo._tool_func(
            s3_key="uploads/user@example.com/sess123/abc_doc.pdf",
            filename="doc.pdf",
        ))

        assert result["success"] is False
        assert "not an image" in result["error"]

    @patch("agent.tools.save_user_photo.user_namespace", return_value="testns123")
    @patch("agent.tools.save_user_photo._s3")
    def test_source_not_found(self, mock_s3, mock_ns):
        from agent.tools.save_user_photo import make_save_user_photo_tool

        save_user_photo = make_save_user_photo_tool("user@example.com")

        mock_s3.head_object.side_effect = Exception("NoSuchKey")

        result = json.loads(save_user_photo._tool_func(
            s3_key="uploads/user@example.com/sess123/nonexistent.jpg",
            filename="nonexistent.jpg",
        ))

        assert result["success"] is False
        assert "Cannot access" in result["error"]

    @patch("agent.tools.save_user_photo.user_namespace", return_value="testns123")
    @patch("agent.tools.save_user_photo._s3")
    def test_appends_to_existing_manifest(self, mock_s3, mock_ns):
        from agent.tools.save_user_photo import make_save_user_photo_tool

        save_user_photo = make_save_user_photo_tool("user@example.com")

        mock_s3.head_object.return_value = {"ContentType": "image/png"}
        mock_s3.copy_object.return_value = {}

        # Existing manifest with one photo
        existing = [{"file_id": "old1", "filename": "old.jpg", "s3_key": "profile/user@example.com/photos/old1.jpg"}]
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(existing).encode()
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_s3.put_object.return_value = {}

        result = json.loads(save_user_photo._tool_func(
            s3_key="uploads/user@example.com/sess123/new.png",
            filename="new.png",
            description="Headshot with glasses",
        ))

        assert result["success"] is True
        assert result["total_photos"] == 2

        # Check manifest was saved with both photos
        put_call = mock_s3.put_object.call_args
        saved_manifest = json.loads(put_call.kwargs["Body"].decode())
        assert len(saved_manifest) == 2
        assert saved_manifest[0]["file_id"] == "old1"
        assert saved_manifest[1]["description"] == "Headshot with glasses"
