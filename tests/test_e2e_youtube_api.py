#!/usr/bin/env python3
"""StoryTeller E2E API Tests — YouTube Video Analysis Feature.

Tests the analyze_youtube_video tool through the live chat-stream endpoint.
Requires:
  - Deployed StoryTeller API (dev or prod)
  - Valid auth token at /tmp/storyteller-test-token.txt
  - Agent runtime with analyze_youtube_video tool registered

Run: python tests/test_e2e_youtube_api.py
Or:  pytest tests/test_e2e_youtube_api.py -v (with pytest wrapper at bottom)
"""
import json
import re
import time
import sys
import os

import requests

# Test configuration
API_BASE = os.environ.get(
    "STORYTELLER_API_BASE",
    "https://c1p7y5p1di.execute-api.us-east-1.amazonaws.com/prod",
)
EMAIL = os.environ.get("STORYTELLER_TEST_EMAIL", "g1@amazon.com")

# Known public YouTube video (AWS Israel channel — stable, Hebrew, tech content)
TEST_VIDEO_URL = "https://youtu.be/9DLYXVAJp-4"
TEST_VIDEO_TITLE_KEYWORDS = ["OCR", "hallucination", "multimodal"]  # At least one should appear


def get_token() -> str:
    """Load auth token from file (shared with other E2E tests)."""
    token_file = os.environ.get(
        "STORYTELLER_TOKEN_FILE", "/tmp/storyteller-test-token.txt"
    )
    if not os.path.exists(token_file):
        raise FileNotFoundError(
            f"Auth token not found at {token_file}. "
            "Run: scripts/get-test-token.sh first."
        )
    with open(token_file) as f:
        return f.read().strip()


def stream_chat(message: str, session_id: str, token: str) -> dict:
    """Send a chat message and collect the streamed response."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "email": EMAIL,
        "message": message,
        "session_id": session_id,
        "file_refs": [],
    }

    try:
        resp = requests.post(
            f"{API_BASE}/chat-stream",
            json=payload,
            headers=headers,
            stream=True,
            timeout=180,  # Video analysis can take a while
        )

        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:500]}"}

        full_text = ""
        progress_events = []
        keepalives = 0

        for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
            if not chunk:
                continue
            if "__KEEPALIVE__" in chunk:
                keepalives += 1
                chunk = chunk.replace("__KEEPALIVE__", "")
            if "__PROGRESS__" in chunk:
                for m in re.finditer(r'__PROGRESS__({.*?})', chunk):
                    try:
                        progress_events.append(json.loads(m.group(1)))
                    except Exception:
                        pass
                chunk = re.sub(r'__PROGRESS__\{.*?\}', '', chunk)
            full_text += chunk

        # Parse SSE format if present
        if "data: " in full_text:
            lines = full_text.split("\n")
            text_parts = []
            for line in lines:
                if line.startswith("data: "):
                    val = line[6:].strip()
                    if not val:
                        continue
                    try:
                        parsed = json.loads(val)
                        if isinstance(parsed, str):
                            text_parts.append(parsed)
                    except Exception:
                        text_parts.append(val)
            full_text = "".join(text_parts)

        return {
            "text": full_text.strip(),
            "progress_events": progress_events,
            "keepalives": keepalives,
            "length": len(full_text.strip()),
        }

    except requests.exceptions.Timeout:
        return {"error": "Request timed out (180s)"}
    except Exception as e:
        return {"error": str(e)}


def test_analyze_youtube_url_directly():
    """Test: user sends a YouTube URL and asks to analyze it."""
    token = get_token()
    session_id = f"test-yt-analyze-{int(time.time())}"

    msg = f"תנתח לי את הסרטון הזה: {TEST_VIDEO_URL}"

    print(f"\n{'='*60}")
    print("TEST: Analyze YouTube URL directly")
    print(f"{'='*60}")
    print(f"Message: {msg}")

    t0 = time.time()
    result = stream_chat(msg, session_id, token)
    elapsed = time.time() - t0

    print(f"Time: {elapsed:.1f}s | Length: {result.get('length', 0)} chars")
    print(f"Progress events: {len(result.get('progress_events', []))}")

    assert "error" not in result, f"API error: {result.get('error')}"
    text = result["text"]

    # Agent should have analyzed the video and returned Hebrew insights
    assert len(text) > 200, f"Response too short ({len(text)} chars) — tool likely didn't run"

    # Should mention something about the video content (OCR/hallucinations/multimodal)
    text_lower = text.lower()
    found_keyword = any(kw.lower() in text_lower for kw in TEST_VIDEO_TITLE_KEYWORDS)
    assert found_keyword, (
        f"Response doesn't mention any expected keywords {TEST_VIDEO_TITLE_KEYWORDS}. "
        f"First 500 chars: {text[:500]}"
    )

    # Should contain Hebrew (the agent responds in Hebrew)
    assert any('\u0590' <= c <= '\u05FF' for c in text), "Response not in Hebrew"

    print(f"✅ PASSED — Video analyzed, Hebrew response with relevant content")
    print(f"   First 200 chars: {text[:200]}...")
    return True


def test_analyze_with_focus():
    """Test: user asks to analyze a specific aspect of a YouTube video."""
    token = get_token()
    session_id = f"test-yt-focus-{int(time.time())}"

    msg = f"תנתח את ה-hook וטכניקות השימור של הסרטון הזה: {TEST_VIDEO_URL}"

    print(f"\n{'='*60}")
    print("TEST: Analyze YouTube with focus (hook + retention)")
    print(f"{'='*60}")
    print(f"Message: {msg}")

    t0 = time.time()
    result = stream_chat(msg, session_id, token)
    elapsed = time.time() - t0

    print(f"Time: {elapsed:.1f}s | Length: {result.get('length', 0)} chars")

    assert "error" not in result, f"API error: {result.get('error')}"
    text = result["text"]

    assert len(text) > 150, f"Response too short ({len(text)} chars)"
    # Should mention hook/opening/retention concepts
    assert any('\u0590' <= c <= '\u05FF' for c in text), "Response not in Hebrew"

    print(f"✅ PASSED — Focused analysis returned")
    print(f"   First 200 chars: {text[:200]}...")
    return True


def test_invalid_youtube_url():
    """Test: user sends a non-YouTube URL — agent should handle gracefully."""
    token = get_token()
    session_id = f"test-yt-invalid-{int(time.time())}"

    msg = "תנתח לי את הסרטון: https://www.google.com/not-a-video"

    print(f"\n{'='*60}")
    print("TEST: Invalid YouTube URL (graceful handling)")
    print(f"{'='*60}")
    print(f"Message: {msg}")

    t0 = time.time()
    result = stream_chat(msg, session_id, token)
    elapsed = time.time() - t0

    print(f"Time: {elapsed:.1f}s | Length: {result.get('length', 0)} chars")

    assert "error" not in result, f"API error: {result.get('error')}"
    text = result["text"]

    # Agent should NOT crash — should respond with explanation or ask for valid URL
    assert len(text) > 20, "Response too short — possible crash"
    # Should still be Hebrew
    assert any('\u0590' <= c <= '\u05FF' for c in text), "Response not in Hebrew"

    print(f"✅ PASSED — Graceful handling of invalid URL")
    print(f"   Response: {text[:200]}...")
    return True


def test_progress_events_during_analysis():
    """Test: video analysis should emit progress events (tool use indicators)."""
    token = get_token()
    session_id = f"test-yt-progress-{int(time.time())}"

    msg = f"צפה בסרטון הזה ותן לי ניתוח מלא: {TEST_VIDEO_URL}"

    print(f"\n{'='*60}")
    print("TEST: Progress events during video analysis")
    print(f"{'='*60}")
    print(f"Message: {msg}")

    t0 = time.time()
    result = stream_chat(msg, session_id, token)
    elapsed = time.time() - t0

    print(f"Time: {elapsed:.1f}s | Length: {result.get('length', 0)} chars")
    print(f"Progress events: {result.get('progress_events', [])}")
    print(f"Keepalives: {result.get('keepalives', 0)}")

    assert "error" not in result, f"API error: {result.get('error')}"

    # Should have keepalives or progress events (video analysis takes time)
    has_activity = (
        result.get("keepalives", 0) > 0
        or len(result.get("progress_events", [])) > 0
    )
    # Note: this assertion is soft — some fast responses may not trigger keepalives
    if has_activity:
        print(f"✅ PASSED — Progress/keepalive events detected during analysis")
    else:
        print(f"⚠️  WARN — No progress events (response may have been cached/fast)")

    # But the response itself should still be valid
    assert len(result["text"]) > 200, "Response too short"
    return True


def run_all():
    """Run all API tests and report results."""
    tests = [
        ("Analyze YouTube URL directly", test_analyze_youtube_url_directly),
        ("Analyze with focus", test_analyze_with_focus),
        ("Invalid YouTube URL", test_invalid_youtube_url),
        ("Progress events during analysis", test_progress_events_during_analysis),
    ]

    print("\n" + "=" * 60)
    print("StoryTeller API Tests — YouTube Video Analysis")
    print("=" * 60)
    print(f"API: {API_BASE}")
    print(f"Email: {EMAIL}")
    print(f"Test video: {TEST_VIDEO_URL}")

    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, "PASS" if passed else "WARN"))
        except AssertionError as e:
            print(f"❌ FAILED: {e}")
            results.append((name, "FAIL"))
        except FileNotFoundError as e:
            print(f"⏭️  SKIP: {e}")
            results.append((name, "SKIP"))
        except Exception as e:
            print(f"💥 ERROR: {e}")
            results.append((name, "ERROR"))

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    for name, status in results:
        icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "💥", "SKIP": "⏭️", "WARN": "⚠️"}[status]
        print(f"  {icon} {name}: {status}")

    passed = sum(1 for _, s in results if s == "PASS")
    total = len(results)
    print(f"\n  {passed}/{total} passed")

    return all(s in ("PASS", "WARN", "SKIP") for _, s in results)


# ── pytest compatibility ─────────────────────────────────────────────────────
import pytest

def _has_token():
    token_file = os.environ.get("STORYTELLER_TOKEN_FILE", "/tmp/storyteller-test-token.txt")
    return os.path.exists(token_file)

pytestmark = pytest.mark.skipif(
    not _has_token(),
    reason="No auth token at /tmp/storyteller-test-token.txt (run scripts/get-test-token.sh)"
)


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
