"""End-to-end tests for YouTube video analysis.

These tests call the actual Gemini API — run only when GEMINI_API_KEY is set
or when we can fetch from Secrets Manager.

Run: pytest tests/test_e2e_youtube_analysis.py -v --tb=short
Skip if no API access: tests auto-skip when credentials are unavailable.
"""

import json
import os
import sys
import pytest

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _has_gemini_access() -> bool:
    """Check if we can access Gemini API (env var or Secrets Manager)."""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return True
    try:
        import boto3
        from botocore.config import Config
        # conftest.py sets fake AWS creds for moto — use instance profile instead
        session = boto3.Session(
            region_name="us-west-2",
        )
        # Force credential refresh from instance metadata (not fake env vars)
        creds = session.get_credentials()
        if creds and creds.access_key == "testing":
            # Fake creds from conftest — create session without them
            clean_env = {k: v for k, v in os.environ.items()
                        if k not in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                                    "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN")}
            import subprocess
            result = subprocess.run(
                [sys.executable, "-c",
                 "import boto3; sm = boto3.client('secretsmanager', region_name='us-west-2'); "
                 "print(sm.get_secret_value(SecretId='gcp/gemini-api-key')['SecretString'][:5])"],
                capture_output=True, text=True,
                env={k: v for k, v in os.environ.items()
                     if k not in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
                                  'AWS_SESSION_TOKEN', 'AWS_SECURITY_TOKEN')}
            )
            return result.returncode == 0
        sm = session.client("secretsmanager")
        sm.get_secret_value(SecretId="gcp/gemini-api-key")
        return True
    except Exception:
        pass
    return False


pytestmark = pytest.mark.skipif(
    not _has_gemini_access(),
    reason="No Gemini API access (set GEMINI_API_KEY or ensure AWS Secrets Manager access)"
)


# Restore real AWS credentials (conftest.py overrides them with 'testing' for moto)
_REAL_CREDS_CLEANED = False

def _restore_real_aws_creds():
    """Remove fake credentials so boto3 falls back to instance profile."""
    global _REAL_CREDS_CLEANED
    if _REAL_CREDS_CLEANED:
        return
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN"):
        os.environ.pop(key, None)
    _REAL_CREDS_CLEANED = True
    # Force re-creation of the secrets client in the tool module
    import agent.tools.analyze_youtube_video as yt_mod
    import boto3
    yt_mod._secrets = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-west-2"))


# Sample public YouTube video for testing (AWS Israel channel - short, stable)
TEST_VIDEO_URL = "https://youtu.be/9DLYXVAJp-4"
TEST_VIDEO_STANDARD = "https://www.youtube.com/watch?v=9DLYXVAJp-4"


class TestYouTubeAnalysisE2E:
    """Live tests against real Gemini API + real YouTube videos."""

    @classmethod
    def setup_class(cls):
        _restore_real_aws_creds()

    def test_basic_analysis(self):
        """Analyze a known video and verify structure."""
        from agent.tools.analyze_youtube_video import analyze_youtube_video

        result = json.loads(analyze_youtube_video._tool_func(youtube_url=TEST_VIDEO_URL))

        assert result["success"] is True
        assert result["video_url"] == TEST_VIDEO_STANDARD
        assert "title_detected" in result or "raw_analysis" in result
        # If structured JSON came back, verify key fields
        if "title_detected" in result:
            assert any(lang in result["language"] for lang in ("Hebrew", "English", "Mixed"))
            assert len(result.get("topics", [])) > 0
            assert "structure" in result
            assert "audience" in result

    def test_analysis_with_focus(self):
        """Focused analysis returns relevant content."""
        from agent.tools.analyze_youtube_video import analyze_youtube_video

        result = json.loads(analyze_youtube_video._tool_func(
            youtube_url=TEST_VIDEO_URL,
            analysis_focus="hook and opening technique"
        ))

        assert result["success"] is True
        # The analysis should exist (either structured or raw)
        assert "title_detected" in result or "raw_analysis" in result

    def test_shorts_url_format(self):
        """Shorts URL format works (may fail if video isn't a short, but shouldn't error)."""
        from agent.tools.analyze_youtube_video import analyze_youtube_video

        # Use standard video URL but formatted as shorts (will normalize)
        result = json.loads(analyze_youtube_video._tool_func(
            youtube_url="https://www.youtube.com/shorts/9DLYXVAJp-4"
        ))

        # Should either succeed or fail gracefully (not crash)
        assert "success" in result

    def test_invalid_video_id(self):
        """Non-existent video ID should fail gracefully."""
        from agent.tools.analyze_youtube_video import analyze_youtube_video

        result = json.loads(analyze_youtube_video._tool_func(
            youtube_url="https://www.youtube.com/watch?v=NONEXISTENT_ID_123"
        ))

        # Should fail gracefully (Gemini will reject or return error)
        # Either success=False OR success=True with limited info
        assert "success" in result

    def test_response_time_reasonable(self):
        """Analysis should complete within 60 seconds."""
        import time
        from agent.tools.analyze_youtube_video import analyze_youtube_video

        start = time.time()
        result = json.loads(analyze_youtube_video._tool_func(youtube_url=TEST_VIDEO_URL))
        elapsed = time.time() - start

        assert result["success"] is True
        assert elapsed < 60, f"Analysis took {elapsed:.1f}s (>60s limit)"
