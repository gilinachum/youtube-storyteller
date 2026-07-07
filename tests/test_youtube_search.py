"""Tests for search_youtube_videos tool — unit tests + live API integration test."""

import json
import pytest
from unittest.mock import patch, MagicMock

from agent.tools.search_youtube_videos import (
    search_youtube_videos,
    _parse_duration,
    _format_views,
)


class TestParseDuration:
    """Test ISO 8601 duration parsing."""

    def test_hours_minutes_seconds(self):
        assert _parse_duration("PT1H2M3S") == "1h2m"

    def test_minutes_seconds(self):
        assert _parse_duration("PT15M42S") == "15m42s"

    def test_minutes_only(self):
        assert _parse_duration("PT7M") == "7m"

    def test_seconds_only(self):
        assert _parse_duration("PT45S") == "45s"

    def test_hours_only(self):
        assert _parse_duration("PT2H") == "2h0m"

    def test_hours_minutes(self):
        assert _parse_duration("PT1H30M") == "1h30m"

    def test_invalid(self):
        assert _parse_duration("") == "?"
        assert _parse_duration("invalid") == "?"
        assert _parse_duration(None) == "?"


class TestFormatViews:
    """Test view count formatting."""

    def test_millions(self):
        assert _format_views("1500000") == "1.5M"

    def test_thousands(self):
        assert _format_views("12500") == "12.5K"

    def test_hundreds(self):
        assert _format_views("500") == "500"

    def test_zero(self):
        assert _format_views("0") == "0"

    def test_invalid(self):
        assert _format_views("") == "?"
        assert _format_views(None) == "?"


class TestSearchYouTubeVideosMocked:
    """Unit tests with mocked API responses."""

    @patch("agent.tools.search_youtube_videos._get_api_key")
    @patch("agent.tools.search_youtube_videos.requests.get")
    def test_successful_search(self, mock_get, mock_key):
        mock_key.return_value = "fake-api-key"

        # Mock search response
        search_response = MagicMock()
        search_response.status_code = 200
        search_response.json.return_value = {
            "items": [
                {
                    "id": {"videoId": "abc123def45"},
                    "snippet": {
                        "title": "Test Video",
                        "channelTitle": "Test Channel",
                        "publishedAt": "2024-01-15T10:00:00Z",
                        "thumbnails": {
                            "high": {"url": "https://i.ytimg.com/vi/abc123def45/hqdefault.jpg"}
                        },
                    },
                }
            ]
        }

        # Mock stats response
        stats_response = MagicMock()
        stats_response.status_code = 200
        stats_response.json.return_value = {
            "items": [
                {
                    "id": "abc123def45",
                    "statistics": {"viewCount": "50000"},
                    "contentDetails": {"duration": "PT10M30S"},
                }
            ]
        }

        mock_get.side_effect = [search_response, stats_response]

        result = json.loads(search_youtube_videos._tool_func(query="test query"))

        assert result["success"] is True
        assert result["total_results"] == 1
        assert len(result["videos"]) == 1

        video = result["videos"][0]
        assert video["video_id"] == "abc123def45"
        assert video["title"] == "Test Video"
        assert video["channel"] == "Test Channel"
        assert video["views"] == "50.0K"
        assert video["duration"] == "10m30s"
        assert video["url"] == "https://www.youtube.com/watch?v=abc123def45"
        assert "thumbnail" in video

    @patch("agent.tools.search_youtube_videos._get_api_key")
    @patch("agent.tools.search_youtube_videos.requests.get")
    def test_no_results(self, mock_get, mock_key):
        mock_key.return_value = "fake-api-key"

        search_response = MagicMock()
        search_response.status_code = 200
        search_response.json.return_value = {"items": []}

        mock_get.return_value = search_response

        result = json.loads(search_youtube_videos._tool_func(query="xyznonexistent12345"))
        assert result["success"] is True
        assert result["videos"] == []

    @patch("agent.tools.search_youtube_videos._get_api_key")
    @patch("agent.tools.search_youtube_videos.requests.get")
    def test_api_error(self, mock_get, mock_key):
        mock_key.return_value = "fake-api-key"

        import requests as req
        error_response = MagicMock()
        error_response.status_code = 403
        error_response.json.return_value = {"error": {"message": "API key invalid"}}
        mock_get.side_effect = req.exceptions.HTTPError(response=error_response)

        result = json.loads(search_youtube_videos._tool_func(query="test"))
        assert result["success"] is False
        assert "error" in result

    @patch("agent.tools.search_youtube_videos._get_api_key")
    @patch("agent.tools.search_youtube_videos.requests.get")
    def test_max_results_clamped(self, mock_get, mock_key):
        """Ensure max_results is clamped between 3 and 15."""
        mock_key.return_value = "fake-api-key"

        search_response = MagicMock()
        search_response.status_code = 200
        search_response.json.return_value = {"items": []}
        mock_get.return_value = search_response

        # Should not crash with out-of-range values
        search_youtube_videos._tool_func(query="test", max_results=100)
        search_youtube_videos._tool_func(query="test", max_results=0)

        # Verify the actual API call uses clamped values
        calls = mock_get.call_args_list
        # First call params should have maxResults=15 (clamped from 100)
        assert calls[0][1]["params"]["maxResults"] == 15
        # Second call params should have maxResults=3 (clamped from 0)
        assert calls[1][1]["params"]["maxResults"] == 3


@pytest.mark.integration
class TestSearchYouTubeVideosLive:
    """Live integration test — hits the real YouTube API.

    Run with: pytest tests/test_youtube_search.py -m integration -v
    Requires: gcp/youtube-api-key secret in AWS Secrets Manager.
    """

    def test_live_search(self):
        """Search for a known topic and verify response structure."""
        result = json.loads(search_youtube_videos._tool_func(
            query="AWS re:Invent 2024 keynote",
            max_results=5,
        ))

        assert result["success"] is True, f"Search failed: {result.get('error')}"
        assert len(result["videos"]) > 0, "Expected at least 1 result"
        assert len(result["videos"]) <= 5

        # Verify structure of first result
        video = result["videos"][0]
        assert "video_id" in video
        assert len(video["video_id"]) == 11  # YouTube IDs are always 11 chars
        assert "title" in video and len(video["title"]) > 0
        assert "channel" in video and len(video["channel"]) > 0
        assert "thumbnail" in video and video["thumbnail"].startswith("https://")
        assert "url" in video and "youtube.com/watch?v=" in video["url"]
        assert "views" in video
        assert "duration" in video
        assert "published" in video and len(video["published"]) == 10  # YYYY-MM-DD

    def test_live_search_hebrew(self):
        """Search with Hebrew query."""
        result = json.loads(search_youtube_videos._tool_func(
            query="בינה מלאכותית AWS",
            max_results=3,
        ))

        assert result["success"] is True, f"Search failed: {result.get('error')}"
        # Hebrew searches should still work
        assert len(result["videos"]) > 0
