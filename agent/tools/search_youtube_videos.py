"""YouTube video search tool using YouTube Data API v3."""

import json
import logging
import os
import re
import threading

import boto3
import requests
from strands import tool

logger = logging.getLogger(__name__)

_api_key = None
_key_lock = threading.Lock()
_secrets = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-west-2"))


def _get_api_key() -> str:
    """Get YouTube Data API key from Secrets Manager (cached)."""
    global _api_key
    if _api_key is not None:
        return _api_key
    with _key_lock:
        if _api_key is not None:
            return _api_key
        _api_key = _secrets.get_secret_value(SecretId="gcp/youtube-api-key")["SecretString"]
        return _api_key


def _parse_duration(iso_duration: str) -> str:
    """Convert ISO 8601 duration (PT1H2M3S) to human-readable format."""
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration or '')
    if not match:
        return "?"
    hours, minutes, seconds = match.groups()
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    elif hours:
        parts.append("0m")
    if seconds and not hours:
        parts.append(f"{seconds}s")
    return "".join(parts) or "?"


def _format_views(count_str: str) -> str:
    """Format view count to human-readable (e.g., 12.5K, 1.2M)."""
    try:
        count = int(count_str)
    except (ValueError, TypeError):
        return "?"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


@tool
def search_youtube_videos(query: str, max_results: int = 10) -> str:
    """Search YouTube for videos matching a query and return structured results.

    Use this tool to find relevant YouTube videos on a topic BEFORE analyzing them.
    Returns a list of videos with titles, thumbnails, view counts, and durations.
    Present these results to the user so they can choose which ones to analyze.

    After the user selects videos, use analyze_youtube_video with the selected URLs.

    Args:
        query: Search query — be specific (e.g., "AWS Bedrock agents tutorial 2024").
        max_results: Number of results to return (5-15, default 10).

    Returns:
        JSON with list of videos including id, title, channel, views, duration, thumbnail URL.
    """
    max_results = max(3, min(15, max_results))

    try:
        api_key = _get_api_key()

        # Step 1: Search for videos
        search_resp = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": max_results,
                "order": "relevance",
                "key": api_key,
            },
            timeout=10,
        )
        search_resp.raise_for_status()
        search_data = search_resp.json()

        items = search_data.get("items", [])
        if not items:
            return json.dumps({
                "success": True,
                "query": query,
                "videos": [],
                "message": "No videos found for this query.",
            }, ensure_ascii=False)

        # Collect video IDs for stats lookup
        video_ids = [item["id"]["videoId"] for item in items]

        # Step 2: Get statistics and duration for all videos in one call
        stats_resp = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "part": "statistics,contentDetails",
                "id": ",".join(video_ids),
                "key": api_key,
            },
            timeout=10,
        )
        stats_resp.raise_for_status()
        stats_data = stats_resp.json()

        # Build stats lookup
        stats_map = {}
        for item in stats_data.get("items", []):
            stats_map[item["id"]] = {
                "views": item.get("statistics", {}).get("viewCount", "0"),
                "duration": item.get("contentDetails", {}).get("duration", ""),
            }

        # Step 3: Combine into structured results
        videos = []
        for item in items:
            video_id = item["id"]["videoId"]
            snippet = item["snippet"]
            stats = stats_map.get(video_id, {})

            videos.append({
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "published": snippet.get("publishedAt", "")[:10],  # YYYY-MM-DD
                "thumbnail": snippet["thumbnails"].get("high", snippet["thumbnails"].get("medium", {})).get("url", f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "views": _format_views(stats.get("views", "0")),
                "views_raw": int(stats.get("views") or 0),
                "duration": _parse_duration(stats.get("duration", "")),
            })

        return json.dumps({
            "success": True,
            "query": query,
            "total_results": len(videos),
            "videos": videos,
        }, ensure_ascii=False, indent=2)

    except requests.exceptions.HTTPError as e:
        error_body = ""
        try:
            error_body = e.response.json().get("error", {}).get("message", str(e))
        except Exception:
            error_body = str(e)
        logger.error("YouTube search API error: %s", error_body)
        return json.dumps({
            "success": False,
            "error": f"YouTube API error: {error_body}",
        }, ensure_ascii=False)

    except Exception as e:
        logger.error("YouTube search failed: %s", e, exc_info=True)
        return json.dumps({
            "success": False,
            "error": f"Search failed: {str(e)}",
        }, ensure_ascii=False)
