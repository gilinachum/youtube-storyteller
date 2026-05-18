# Design: YouTube Video Analysis via Gemini

## Summary

Add the ability for the StoryTeller agent to "watch" existing YouTube videos using Gemini's multimodal video understanding. When a user provides a YouTube URL (or the agent discovers a relevant video during research), Gemini analyzes the video and returns a structured summary — topic, style, pacing, audience level, thumbnail approach, etc. This feeds directly into the planning process for new videos.

## Motivation

- Creators often reference existing videos: "I want something like this video" or "this is what my competitor did"
- Understanding an existing video's structure helps plan better content (avoid overlap, learn from what works)
- Can analyze the creator's own past videos to maintain consistency
- Enables "sequel/response video" planning with full context of the original

## Architecture

### Approach: Gemini Native YouTube URL Support

Gemini models support YouTube video understanding natively via `Part.from_uri()`. You pass a YouTube URL directly — no need to download the video or use the File API.

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=api_key)

response = client.models.generate_content(
    model="gemini-3.1-flash-preview",
    contents=[
        types.Part.from_uri(
            file_uri="https://www.youtube.com/watch?v=VIDEO_ID",
            mime_type="video/*",
        ),
        "Analyze this video: summarize the content, identify the structure, ..."
    ],
)
```

**Why this approach:**
- Zero infrastructure — no video download, no storage, no File API upload
- Fast — Gemini handles YouTube natively (processes audio + visual)
- Cost-effective — uses Gemini 2.5 Flash (cheap, fast, good for analysis)
- Already have GCP API key in Secrets Manager (`gcp/gemini-api-key`)

### Model Choice

Use `gemini-3.1-flash-preview` for video analysis:
- Supports video understanding (audio + visual frames)
- Fast and cheap (this is analysis, not generation)
- Thinking enabled for better structured output
- Reserve `gemini-3.1-flash-image-preview` for thumbnail generation only

## New Tool: `analyze_youtube_video`

### File Location
`agent/tools/analyze_youtube_video.py`

### Interface

```python
@tool
def analyze_youtube_video(youtube_url: str, analysis_focus: str = "") -> str:
    """Analyze an existing YouTube video using Gemini video understanding.

    Args:
        youtube_url: Full YouTube URL (https://www.youtube.com/watch?v=... or https://youtu.be/...)
        analysis_focus: Optional specific focus for analysis. Examples:
            - "structure and pacing" 
            - "hook and retention techniques"
            - "thumbnail and title strategy"
            - "audience engagement patterns"
            If empty, returns a comprehensive general analysis.

    Returns:
        JSON with structured analysis: summary, topics, structure, 
        style, audience level, key takeaways, and planning recommendations.
    """
```

### Output Structure (JSON)

```json
{
  "success": true,
  "video_url": "https://www.youtube.com/watch?v=...",
  "title_detected": "Video title as spoken/shown",
  "language": "Hebrew/English/Mixed",
  "duration_estimate": "~5 minutes",
  "summary": "Brief 2-3 sentence summary of what the video covers",
  "topics": ["topic1", "topic2", "topic3"],
  "structure": {
    "hook": "How the video opens (first 15s)",
    "sections": [
      {"name": "Section name", "duration": "~1m", "content": "What's covered"}
    ],
    "closing": "How the video ends / CTA"
  },
  "style": {
    "presentation_type": "talking head / screencast / slides / mixed",
    "energy_level": "high / medium / low",
    "editing_pace": "fast cuts / medium / slow",
    "visual_elements": ["screen recording", "animations", "text overlays"]
  },
  "audience": {
    "level": "L100/L200/L300/L400",
    "target": "developers / managers / beginners / etc."
  },
  "thumbnail_observations": "What the thumbnail shows (if visible)",
  "planning_recommendations": "How this video could inform new content planning"
}
```

### Implementation Details

```python
"""Analyze YouTube videos using Gemini video understanding."""

import json
import logging
import os
import re

import boto3
from strands import tool

logger = logging.getLogger(__name__)

_gemini_client = None
_secrets = boto3.client("secretsmanager")

ANALYSIS_MODEL = "gemini-3.1-flash-preview"


def _get_gemini_client():
    """Get or create the Gemini client (lazy init)."""
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        api_key = _secrets.get_secret_value(SecretId="gcp/gemini-api-key")["SecretString"]
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _normalize_youtube_url(url: str) -> str:
    """Normalize various YouTube URL formats to standard watch URL."""
    # Handle youtu.be/ID
    match = re.match(r'https?://youtu\.be/([a-zA-Z0-9_-]+)', url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    # Handle youtube.com/shorts/ID
    match = re.match(r'https?://(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]+)', url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    # Already standard format
    return url


@tool
def analyze_youtube_video(youtube_url: str, analysis_focus: str = "") -> str:
    """Analyze an existing YouTube video using Gemini video understanding.

    Use this when you need to understand what an existing YouTube video covers,
    its structure, style, or any other aspect. Useful for:
    - Understanding a reference video the user shared
    - Analyzing competitor content
    - Reviewing the user's own past videos for consistency
    - Planning sequel/follow-up videos

    Args:
        youtube_url: Full YouTube URL (youtube.com/watch?v=, youtu.be/, or youtube.com/shorts/)
        analysis_focus: Optional specific focus for the analysis.
            Examples: "structure and pacing", "hook and retention",
            "thumbnail and title strategy", "audience and level".
            If empty, returns comprehensive general analysis.

    Returns:
        JSON with structured video analysis including summary, topics,
        structure breakdown, style notes, audience level, and recommendations.
    """
    from google.genai import types

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
                temperature=0.2,  # Low temp for factual analysis
            ),
        )

        result_text = response.text.strip()
        
        # Try to parse as JSON to validate
        try:
            # Strip markdown fencing if present
            if result_text.startswith("```"):
                result_text = re.sub(r'^```(?:json)?\n?', '', result_text)
                result_text = re.sub(r'\n?```$', '', result_text)
            parsed = json.loads(result_text)
            parsed["success"] = True
            parsed["video_url"] = normalized_url
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            # Return raw text if not valid JSON
            return json.dumps({
                "success": True,
                "video_url": normalized_url,
                "raw_analysis": result_text,
            }, ensure_ascii=False)

    except Exception as e:
        logger.error("YouTube video analysis failed: %s", e, exc_info=True)
        error_msg = str(e)
        
        # Provide helpful error messages
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
```

## System Prompt Changes

Add to the system prompt (in the "Available Tools" section):

```
- **analyze_youtube_video** — analyze an existing YouTube video. Give it a YouTube URL and optionally
  a specific focus area (e.g., "structure and pacing", "hook techniques"). Returns a structured
  breakdown of the video's content, style, audience level, and structure. Use this when:
  - The user shares a YouTube link as reference ("I want something like this")
  - You need to understand a competitor's video
  - The user wants to plan a sequel/follow-up to an existing video
  - Reviewing the user's own past videos for consistency
```

Add a new section to the system prompt (before "Conversation Flow"):

```markdown
# YouTube Video Analysis Capability

You can **watch and analyze existing YouTube videos** to inform content planning.

## When to Use
- User shares a YouTube URL → offer to analyze it
- User mentions an existing video they made → ask for the link, analyze for consistency
- Competitive analysis → analyze competitor videos for style/structure insights
- Sequel planning → analyze the original video before planning part 2
- **After research** → if deep_research returns YouTube URLs in its results, proactively analyze the most relevant ones (up to 2-3) to enrich your findings

## How to Communicate
- "🎬 צופה בסרטון ומנתח..." (while analyzing)
- After analysis, present key findings naturally in Hebrew
- Connect findings to the current planning task: "בסרטון הזה הוא משתמש ב-hook של שאלה — אפשר לעשות משהו דומה"
- Don't dump raw JSON to the user — summarize the insights conversationally

## Proactive Use After Research

When you run `deep_research` and the results contain YouTube video URLs:
1. Identify the 2-3 most relevant videos (by title/context match to the topic)
2. Call `analyze_youtube_video` on each one
3. Include the video insights in your research summary:
   - What angle each video took
   - What content level (L100-L400) they targeted
   - What gaps they left (opportunities for the user's video)
   - Style/format observations
4. Tell the user: "מצאתי X סרטונים רלוונטיים בנושא וצפיתי בהם — הנה מה שלמדתי:"

This helps the user understand the competitive landscape and find unique angles.

## Limitations
- Works on public YouTube videos (not private/unlisted unless accessible)
- Very long videos (2h+) may hit token limits — suggest focusing on specific timestamps
- Analysis quality depends on video clarity (audio + visual)
```

## Integration Points

### 1. Tool Registration (`runtime_app.py` or wherever tools are assembled)
```python
from agent.tools.analyze_youtube_video import analyze_youtube_video
# Add to tools list
```

### 2. `__init__.py` Update
```python
from .analyze_youtube_video import analyze_youtube_video
```

### 3. deep_research Integration
When `deep_research` discovers relevant YouTube videos during web research, the agent should proactively analyze the top 2-3 most relevant ones using `analyze_youtube_video`. This is a system prompt instruction (not a code change to deep_research) — the agent decides to call the tool based on research results.

## Cost Estimate

- Gemini 2.5 Flash video input: ~$0.001-0.005 per video (depending on length)
- Typical 5-min YouTube video: ~$0.002 per analysis
- Very affordable — no need for rate limiting beyond Gemini's own quotas

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Video is private/age-restricted | Graceful error message with explanation |
| Video too long (2h+) | Warn user, suggest timestamp focus |
| Gemini YouTube support changes | Fallback: download via yt-dlp + File API upload |
| Rate limiting from Google | Lazy client init, no batch processing |
| Non-YouTube video URLs | Validate URL format before calling Gemini |

## Rollout Plan

1. **Phase 1** (this PR): New `analyze_youtube_video` tool + system prompt updates + post-research proactive analysis instruction
2. **Phase 2**: Video comparison feature ("compare my video to this one")
3. **Phase 3**: Automatic series detection ("this is part 3 of a series, here's what parts 1-2 covered")

## Files to Change

| File | Change |
|------|--------|
| `agent/tools/analyze_youtube_video.py` | **NEW** — the tool implementation |
| `agent/tools/__init__.py` | Add import + export |
| `agent/system_prompt.py` | Add tool description + YouTube analysis section |
| `agent/runtime_app.py` | Register the new tool |
| `tests/test_youtube_analysis.py` | **NEW** — unit tests |
| `requirements.txt` | Verify `google-genai` is already there (it is, for thumbnails) |

## Dependencies

- `google-genai` — already installed (used by thumbnail generation)
- `gcp/gemini-api-key` — already in Secrets Manager
- No new infrastructure needed
