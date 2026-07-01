"""Analyze YouTube videos using Gemini video understanding."""

import json
import logging
import os
import re
import threading

import boto3
from strands import tool

logger = logging.getLogger(__name__)

# Thread-safe client initialization
_gemini_client = None
_client_lock = threading.Lock()
_secrets = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-west-2"))

# Use Gemini 3 Flash for video analysis (fast, multimodal, cheap)
ANALYSIS_MODEL = "gemini-3-flash-preview"

# Timeout for Gemini API call (video analysis can be slow for long videos)
ANALYSIS_TIMEOUT_SECONDS = 120


def _get_gemini_client():
    """Get or create the Gemini client (thread-safe lazy init)."""
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    with _client_lock:
        # Double-check after acquiring lock
        if _gemini_client is not None:
            return _gemini_client
        from google import genai
        api_key = _secrets.get_secret_value(SecretId="gcp/gemini-api-key")["SecretString"]
        _gemini_client = genai.Client(api_key=api_key)
        return _gemini_client


# ── YouTube URL patterns ─────────────────────────────────────────────────────
# All known formats users might paste:
#   https://www.youtube.com/watch?v=ID
#   https://www.youtube.com/watch?v=ID&t=120&list=PLxyz
#   https://youtube.com/watch?v=ID
#   https://m.youtube.com/watch?v=ID
#   https://youtu.be/ID
#   https://youtu.be/ID?t=30
#   https://www.youtube.com/shorts/ID
#   https://youtube.com/shorts/ID
#   https://www.youtube.com/embed/ID
#   https://www.youtube.com/v/ID
#   https://www.youtube.com/live/ID
#   http:// variants of all above

_VIDEO_ID_PATTERN = r'[a-zA-Z0-9_-]{11}'  # YouTube IDs are always 11 chars

_YOUTUBE_PATTERNS = [
    # Standard watch URL (v= can be anywhere in query string)
    re.compile(rf'https?://(?:www\.|m\.)?youtube\.com/watch\?.*v=({_VIDEO_ID_PATTERN})'),
    # Short URL
    re.compile(rf'https?://youtu\.be/({_VIDEO_ID_PATTERN})'),
    # Shorts
    re.compile(rf'https?://(?:www\.|m\.)?youtube\.com/shorts/({_VIDEO_ID_PATTERN})'),
    # Embed
    re.compile(rf'https?://(?:www\.|m\.)?youtube\.com/embed/({_VIDEO_ID_PATTERN})'),
    # Old /v/ format
    re.compile(rf'https?://(?:www\.|m\.)?youtube\.com/v/({_VIDEO_ID_PATTERN})'),
    # Live streams
    re.compile(rf'https?://(?:www\.|m\.)?youtube\.com/live/({_VIDEO_ID_PATTERN})'),
]


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from any known URL format. Returns None if not a YouTube URL."""
    if not url:
        return None
    for pattern in _YOUTUBE_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def _normalize_youtube_url(url: str) -> str:
    """Normalize any YouTube URL format to standard watch URL."""
    video_id = _extract_video_id(url)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    # Fallback: return as-is
    return url


def _is_youtube_url(url: str) -> bool:
    """Check if a URL is a YouTube video URL."""
    return _extract_video_id(url) is not None


@tool
def analyze_youtube_video(youtube_url: str = "", analysis_focus: str = "", youtube_urls: list = None) -> str:
    """Analyze one or more YouTube videos using Gemini video understanding.

    Use this when you need to understand what existing YouTube videos cover,
    their structure, style, or any other aspect. Useful for:
    - Understanding a reference video the user shared
    - Analyzing competitor content
    - Reviewing the user's own past videos for consistency
    - Planning sequel/follow-up videos
    - Enriching research results when YouTube URLs are found

    IMPORTANT: When analyzing multiple videos, pass them ALL in youtube_urls
    to analyze them in parallel (much faster than calling this tool multiple times).

    Args:
        youtube_url: Single YouTube URL (for backwards compatibility).
        analysis_focus: Optional specific focus for the analysis.
            Examples: "structure and pacing", "hook and retention",
            "thumbnail and title strategy", "audience and level".
            If empty, returns comprehensive general analysis.
        youtube_urls: List of YouTube URLs to analyze in parallel.
            Use this when you have 2+ videos to analyze.

    Returns:
        JSON with structured video analysis including summary, topics,
        structure breakdown, style notes, audience level, and recommendations.
    """
    import concurrent.futures

    # Collect all URLs
    urls = []
    if youtube_urls:
        urls.extend(youtube_urls)
    if youtube_url and youtube_url not in urls:
        urls.append(youtube_url)

    if not urls:
        return json.dumps({"success": False, "error": "No YouTube URL provided"}, ensure_ascii=False)

    # Single URL — run directly
    if len(urls) == 1:
        return _analyze_single_video(urls[0], analysis_focus)

    # Multiple URLs — run in parallel
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_analyze_single_video, url, analysis_focus): url for url in urls[:3]}
        for future in concurrent.futures.as_completed(futures):
            url = futures[future]
            try:
                result = future.result(timeout=ANALYSIS_TIMEOUT_SECONDS)
                results.append(json.loads(result))
            except Exception as e:
                results.append({"success": False, "video_url": url, "error": str(e)})

    return json.dumps({"success": True, "videos": results}, ensure_ascii=False, indent=2)


def _analyze_single_video(youtube_url: str, analysis_focus: str = "") -> str:
    """Analyze a single YouTube video (internal implementation)."""
    from google.genai import types

    # Validate URL
    if not _is_youtube_url(youtube_url):
        return json.dumps({
            "success": False,
            "error": f"Not a valid YouTube URL: {youtube_url}",
            "hint": "Supported formats: youtube.com/watch?v=ID, youtu.be/ID, youtube.com/shorts/ID, youtube.com/embed/ID, youtube.com/live/ID",
        }, ensure_ascii=False)

    client = _get_gemini_client()
    normalized_url = _normalize_youtube_url(youtube_url)

    # Build the analysis prompt
    base_prompt = """Analyze this YouTube video thoroughly and return a JSON response with this exact structure:
{
  "title_detected": "the video title as shown or spoken",
  "language": "primary language (Hebrew/English/Mixed)",
  "duration_estimate": "estimated duration",
  "summary": "2-3 sentence summary of the video content",
  "topics": ["main topic 1", "main topic 2", ...],
  "structure": {
    "hook": "how the video opens (first 15 seconds)",
    "sections": [
      {"name": "section name", "duration": "approx duration", "content": "what's covered"}
    ],
    "closing": "how the video ends / call to action"
  },
  "style": {
    "presentation_type": "talking head / screencast / slides / mixed",
    "energy_level": "high / medium / low",
    "editing_pace": "fast cuts / medium / slow",
    "visual_elements": ["list of visual techniques used"]
  },
  "audience": {
    "level": "L100/L200/L300/L400",
    "target": "target audience description"
  },
  "thumbnail_observations": "what the video thumbnail shows if visible",
  "planning_recommendations": "how this could inform planning new content"
}

Return ONLY valid JSON, no markdown fencing."""

    if analysis_focus:
        base_prompt += f"\n\nFocus especially on: {analysis_focus}"

    try:
        response = client.models.generate_content(
            model=ANALYSIS_MODEL,
            contents=[
                types.Part.from_uri(
                    file_uri=normalized_url,
                    mime_type="video/*",
                ),
                base_prompt,
            ],
            config=types.GenerateContentConfig(
                temperature=0.2,
                http_options=types.HttpOptions(timeout=ANALYSIS_TIMEOUT_SECONDS * 1000),
            ),
        )

        result_text = response.text.strip()

        # Try to parse as JSON to validate
        try:
            if result_text.startswith("```"):
                result_text = re.sub(r'^```(?:json)?\n?', '', result_text)
                result_text = re.sub(r'\n?```$', '', result_text)
            parsed = json.loads(result_text)
            parsed["success"] = True
            parsed["video_url"] = normalized_url
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return json.dumps({
                "success": True,
                "video_url": normalized_url,
                "raw_analysis": result_text,
            }, ensure_ascii=False)

    except TimeoutError:
        return json.dumps({
            "success": False,
            "error": "Video analysis timed out (2 minute limit).",
            "hint": "The video may be too long. Try asking about a specific aspect instead.",
        }, ensure_ascii=False)

    except Exception as e:
        logger.error("YouTube video analysis failed: %s", e, exc_info=True)
        error_msg = str(e)

        # Detect timeout-like errors from httpx/aiohttp
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            return json.dumps({
                "success": False,
                "error": "Video analysis timed out (2 minute limit).",
                "hint": "The video may be too long. Try asking about a specific aspect instead.",
            }, ensure_ascii=False)

        if "not supported" in error_msg.lower() or "invalid" in error_msg.lower():
            return json.dumps({
                "success": False,
                "error": f"Video analysis failed: {error_msg}",
                "hint": "The video may be private, age-restricted, or too long for analysis.",
            }, ensure_ascii=False)

        return json.dumps({
            "success": False,
            "error": error_msg,
        }, ensure_ascii=False)
