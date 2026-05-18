"""Unit tests for YouTube video analysis tool."""

import json
import pytest
from unittest.mock import patch, MagicMock

from agent.tools.analyze_youtube_video import (
    analyze_youtube_video,
    _normalize_youtube_url,
    _is_youtube_url,
    _extract_video_id,
)


class TestExtractVideoId:
    """Test video ID extraction from all known YouTube URL formats."""

    def test_standard_watch(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_watch_no_www(self):
        assert _extract_video_id("https://youtube.com/watch?v=9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_watch_mobile(self):
        assert _extract_video_id("https://m.youtube.com/watch?v=9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_watch_with_extra_params_before_v(self):
        assert _extract_video_id("https://www.youtube.com/watch?list=PLxyz&v=9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_watch_with_extra_params_after_v(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=9DLYXVAJp-4&t=120&list=PLxyz") == "9DLYXVAJp-4"

    def test_watch_http(self):
        assert _extract_video_id("http://www.youtube.com/watch?v=9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_short_url(self):
        assert _extract_video_id("https://youtu.be/9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_short_url_with_timestamp(self):
        assert _extract_video_id("https://youtu.be/9DLYXVAJp-4?t=30") == "9DLYXVAJp-4"

    def test_short_url_http(self):
        assert _extract_video_id("http://youtu.be/9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_shorts(self):
        assert _extract_video_id("https://www.youtube.com/shorts/9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_shorts_no_www(self):
        assert _extract_video_id("https://youtube.com/shorts/9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_shorts_mobile(self):
        assert _extract_video_id("https://m.youtube.com/shorts/9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_embed(self):
        assert _extract_video_id("https://www.youtube.com/embed/9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_embed_with_params(self):
        assert _extract_video_id("https://www.youtube.com/embed/9DLYXVAJp-4?autoplay=1") == "9DLYXVAJp-4"

    def test_old_v_format(self):
        assert _extract_video_id("https://www.youtube.com/v/9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_live(self):
        assert _extract_video_id("https://www.youtube.com/live/9DLYXVAJp-4") == "9DLYXVAJp-4"

    def test_live_with_params(self):
        assert _extract_video_id("https://www.youtube.com/live/9DLYXVAJp-4?si=abc123") == "9DLYXVAJp-4"

    # ── Invalid URLs ──

    def test_invalid_google(self):
        assert _extract_video_id("https://www.google.com") is None

    def test_invalid_channel(self):
        assert _extract_video_id("https://www.youtube.com/@channel") is None

    def test_invalid_playlist(self):
        assert _extract_video_id("https://www.youtube.com/playlist?list=PLxyz") is None

    def test_invalid_empty(self):
        assert _extract_video_id("") is None

    def test_invalid_none_like(self):
        assert _extract_video_id("not a url") is None

    def test_invalid_youtube_homepage(self):
        assert _extract_video_id("https://www.youtube.com/") is None

    def test_invalid_youtube_results(self):
        assert _extract_video_id("https://www.youtube.com/results?search_query=test") is None


class TestNormalizeYouTubeUrl:
    """Test URL normalization for various YouTube formats."""

    def test_standard_watch_url(self):
        url = "https://www.youtube.com/watch?v=9DLYXVAJp-4"
        assert _normalize_youtube_url(url) == url

    def test_short_url(self):
        url = "https://youtu.be/9DLYXVAJp-4"
        assert _normalize_youtube_url(url) == "https://www.youtube.com/watch?v=9DLYXVAJp-4"

    def test_shorts_url(self):
        url = "https://www.youtube.com/shorts/9DLYXVAJp-4"
        assert _normalize_youtube_url(url) == "https://www.youtube.com/watch?v=9DLYXVAJp-4"

    def test_no_www(self):
        url = "https://youtube.com/shorts/9DLYXVAJp-4"
        assert _normalize_youtube_url(url) == "https://www.youtube.com/watch?v=9DLYXVAJp-4"

    def test_embed_normalized(self):
        url = "https://www.youtube.com/embed/9DLYXVAJp-4"
        assert _normalize_youtube_url(url) == "https://www.youtube.com/watch?v=9DLYXVAJp-4"

    def test_live_normalized(self):
        url = "https://www.youtube.com/live/9DLYXVAJp-4"
        assert _normalize_youtube_url(url) == "https://www.youtube.com/watch?v=9DLYXVAJp-4"

    def test_mobile_normalized(self):
        url = "https://m.youtube.com/watch?v=9DLYXVAJp-4"
        assert _normalize_youtube_url(url) == "https://www.youtube.com/watch?v=9DLYXVAJp-4"

    def test_extra_params_stripped(self):
        url = "https://www.youtube.com/watch?v=9DLYXVAJp-4&t=120&list=PLxyz"
        # Normalized to clean watch URL (ID only)
        assert _normalize_youtube_url(url) == "https://www.youtube.com/watch?v=9DLYXVAJp-4"


class TestIsYouTubeUrl:
    """Test YouTube URL validation."""

    def test_valid_watch(self):
        assert _is_youtube_url("https://www.youtube.com/watch?v=9DLYXVAJp-4")

    def test_valid_short(self):
        assert _is_youtube_url("https://youtu.be/9DLYXVAJp-4")

    def test_valid_shorts(self):
        assert _is_youtube_url("https://www.youtube.com/shorts/9DLYXVAJp-4")

    def test_valid_embed(self):
        assert _is_youtube_url("https://www.youtube.com/embed/9DLYXVAJp-4")

    def test_valid_live(self):
        assert _is_youtube_url("https://www.youtube.com/live/9DLYXVAJp-4")

    def test_valid_mobile(self):
        assert _is_youtube_url("https://m.youtube.com/watch?v=9DLYXVAJp-4")

    def test_invalid_url(self):
        assert not _is_youtube_url("https://www.google.com")

    def test_invalid_youtube_channel(self):
        assert not _is_youtube_url("https://www.youtube.com/@channel")

    def test_invalid_empty(self):
        assert not _is_youtube_url("")

    def test_invalid_playlist(self):
        assert not _is_youtube_url("https://www.youtube.com/playlist?list=PLxyz")


class TestAnalyzeYouTubeVideo:
    """Test the main analysis tool function."""

    def test_invalid_url_returns_error(self):
        """Non-YouTube URLs should return error without calling Gemini."""
        result = json.loads(analyze_youtube_video._tool_func(youtube_url="https://www.google.com"))
        assert result["success"] is False
        assert "Not a valid YouTube URL" in result["error"]

    def test_empty_url_returns_error(self):
        result = json.loads(analyze_youtube_video._tool_func(youtube_url=""))
        assert result["success"] is False

    @patch("agent.tools.analyze_youtube_video._get_gemini_client")
    def test_successful_analysis(self, mock_get_client):
        """Successful Gemini response is parsed and returned."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "title_detected": "Test Video",
            "language": "Hebrew",
            "duration_estimate": "5 minutes",
            "summary": "A test video about testing",
            "topics": ["testing", "automation"],
            "structure": {
                "hook": "Opens with a question",
                "sections": [{"name": "Intro", "duration": "1m", "content": "Overview"}],
                "closing": "Subscribe CTA"
            },
            "style": {
                "presentation_type": "screencast",
                "energy_level": "medium",
                "editing_pace": "medium",
                "visual_elements": ["code editor", "terminal"]
            },
            "audience": {"level": "L200", "target": "developers"},
            "thumbnail_observations": "Code on dark background",
            "planning_recommendations": "Good for follow-up deep dive"
        })
        mock_client.models.generate_content.return_value = mock_response

        result = json.loads(analyze_youtube_video._tool_func(
            youtube_url="https://www.youtube.com/watch?v=9DLYXVAJp-4"
        ))

        assert result["success"] is True
        assert result["video_url"] == "https://www.youtube.com/watch?v=9DLYXVAJp-4"
        assert result["title_detected"] == "Test Video"
        assert result["audience"]["level"] == "L200"

    @patch("agent.tools.analyze_youtube_video._get_gemini_client")
    def test_analysis_with_focus(self, mock_get_client):
        """Focus parameter is included in the prompt."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"title_detected": "Test", "summary": "test"}'
        mock_client.models.generate_content.return_value = mock_response

        analyze_youtube_video._tool_func(
            youtube_url="https://youtu.be/9DLYXVAJp-4",
            analysis_focus="hook and retention"
        )

        # Verify the prompt includes the focus
        call_args = mock_client.models.generate_content.call_args
        contents = call_args.kwargs.get("contents") or call_args[1].get("contents")
        prompt_text = contents[1]  # Second content part is the text prompt
        assert "hook and retention" in prompt_text

    @patch("agent.tools.analyze_youtube_video._get_gemini_client")
    def test_gemini_error_handled(self, mock_get_client):
        """Gemini API errors are handled gracefully."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception("API quota exceeded")

        result = json.loads(analyze_youtube_video._tool_func(
            youtube_url="https://www.youtube.com/watch?v=9DLYXVAJp-4"
        ))

        assert result["success"] is False
        assert "API quota exceeded" in result["error"]

    @patch("agent.tools.analyze_youtube_video._get_gemini_client")
    def test_timeout_error_handled(self, mock_get_client):
        """Timeout errors return a helpful message."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content.side_effect = TimeoutError("Connection timed out")

        result = json.loads(analyze_youtube_video._tool_func(
            youtube_url="https://www.youtube.com/watch?v=9DLYXVAJp-4"
        ))

        assert result["success"] is False
        assert "timed out" in result["error"]
        assert "hint" in result

    @patch("agent.tools.analyze_youtube_video._get_gemini_client")
    def test_httpx_timeout_handled(self, mock_get_client):
        """httpx-style timeout errors also caught."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception("ReadTimeout: timed out waiting for response")

        result = json.loads(analyze_youtube_video._tool_func(
            youtube_url="https://www.youtube.com/watch?v=9DLYXVAJp-4"
        ))

        assert result["success"] is False
        assert "timed out" in result["error"]

    @patch("agent.tools.analyze_youtube_video._get_gemini_client")
    def test_non_json_response_handled(self, mock_get_client):
        """Non-JSON Gemini response is returned as raw_analysis."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = "This is a free-form analysis of the video..."
        mock_client.models.generate_content.return_value = mock_response

        result = json.loads(analyze_youtube_video._tool_func(
            youtube_url="https://www.youtube.com/watch?v=9DLYXVAJp-4"
        ))

        assert result["success"] is True
        assert "raw_analysis" in result
        assert "free-form analysis" in result["raw_analysis"]

    @patch("agent.tools.analyze_youtube_video._get_gemini_client")
    def test_markdown_fenced_json_stripped(self, mock_get_client):
        """Gemini sometimes returns JSON wrapped in markdown code fences."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '```json\n{"title_detected": "Test", "summary": "works"}\n```'
        mock_client.models.generate_content.return_value = mock_response

        result = json.loads(analyze_youtube_video._tool_func(
            youtube_url="https://www.youtube.com/watch?v=9DLYXVAJp-4"
        ))

        assert result["success"] is True
        assert result["title_detected"] == "Test"

    @patch("agent.tools.analyze_youtube_video._get_gemini_client")
    def test_embed_url_normalized_before_api(self, mock_get_client):
        """Embed URLs are normalized to standard watch format."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"title_detected": "Test"}'
        mock_client.models.generate_content.return_value = mock_response

        result = json.loads(analyze_youtube_video._tool_func(
            youtube_url="https://www.youtube.com/embed/9DLYXVAJp-4"
        ))

        assert result["video_url"] == "https://www.youtube.com/watch?v=9DLYXVAJp-4"

    @patch("agent.tools.analyze_youtube_video._get_gemini_client")
    def test_youtu_be_normalized_before_api_call(self, mock_get_client):
        """Short URLs are normalized before sending to Gemini."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"title_detected": "Test"}'
        mock_client.models.generate_content.return_value = mock_response

        result = json.loads(analyze_youtube_video._tool_func(
            youtube_url="https://youtu.be/9DLYXVAJp-4"
        ))

        assert result["video_url"] == "https://www.youtube.com/watch?v=9DLYXVAJp-4"


class TestThreadSafety:
    """Test thread-safe client initialization."""

    @patch("agent.tools.analyze_youtube_video._gemini_client", None)
    @patch("agent.tools.analyze_youtube_video._secrets")
    def test_client_created_once_under_concurrent_access(self, mock_secrets):
        """Multiple threads should not create multiple clients."""
        import threading
        import importlib
        yt_mod = importlib.import_module("agent.tools.analyze_youtube_video")

        mock_secrets.get_secret_value.return_value = {"SecretString": "fake-key"}

        with patch("google.genai.Client") as mock_genai_client:
            mock_genai_client.return_value = MagicMock()

            results = []
            def get_client():
                client = yt_mod._get_gemini_client()
                results.append(id(client))

            threads = [threading.Thread(target=get_client) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # All threads should get the same client instance
            assert len(set(results)) == 1, f"Got {len(set(results))} different client instances"
