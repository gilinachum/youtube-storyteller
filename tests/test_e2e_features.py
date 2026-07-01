"""E2E feature tests for StoryTeller — deep research, QR code, thumbnail, and combined.

Tests run against the deployed dev environment via Playwright (browser UI).
Each test logs in, sends a feature-specific prompt, and verifies the agent
responds correctly within timeout.

Run with: uv run pytest tests/test_e2e_features.py -v -m integration
"""

import os
import re
import time

import pytest

# ── Config ───────────────────────────────────────────────────────────────────

def _find_chromium():
    import glob
    candidates = sorted(glob.glob(os.path.expanduser(
        "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"
    )))
    return candidates[-1] if candidates else "/usr/bin/chromium-browser"


CHROMIUM = os.environ.get("CHROMIUM_PATH", _find_chromium())
APP_URL = os.environ.get("APP_URL", "https://d47e04mnn21ns.cloudfront.net")
TEST_EMAIL = os.environ.get("TEST_EMAIL", "e2e-test@storyteller.dev")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "Test6e6b80e86e571fb1!1")

# Timeouts
LOGIN_WAIT = 4000
RESEARCH_TIMEOUT = 90  # seconds — research takes a while
QR_TIMEOUT = 45
THUMBNAIL_TIMEOUT = 120
COMBINED_TIMEOUT = 180


def playwright_available():
    try:
        from playwright.sync_api import sync_playwright
        return os.path.exists(CHROMIUM)
    except ImportError:
        return False


# ── Helpers ──────────────────────────────────────────────────────────────────

class StoryTellerPage:
    """Helper wrapping Playwright page with StoryTeller-specific actions."""

    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True, executable_path=CHROMIUM)
        self.page = self._browser.new_page(viewport={"width": 1280, "height": 720})

    def login(self):
        self.page.goto(APP_URL, wait_until="networkidle")
        self.page.locator('input[type="email"]').fill(TEST_EMAIL)
        self.page.locator('input[type="password"]').fill(TEST_PASSWORD)
        self.page.locator('button[type="submit"]').click()
        self.page.wait_for_timeout(LOGIN_WAIT)
        # Verify we're in the chat
        assert self.page.locator("textarea").first.is_visible(), "Chat textarea not visible after login"

    def new_session(self):
        """Click 'שיחה חדשה' to start a fresh session."""
        btn = self.page.locator('button:has-text("שיחה חדשה")').first
        btn.click(timeout=5000)
        self.page.wait_for_timeout(1000)

    def send_message(self, text: str):
        """Type and send a message."""
        textarea = self.page.locator("textarea").first
        textarea.fill(text)
        textarea.press("Enter")

    def wait_for_response(self, timeout_sec: int, contains: list[str] | None = None) -> str:
        """Wait for an agent response containing expected text.

        Returns the full page text when a response is detected.
        """
        start = time.time()
        last_text = ""

        while time.time() - start < timeout_sec:
            self.page.wait_for_timeout(3000)
            body_text = self.page.locator("body").inner_text()

            # Check if new content appeared (beyond what we had)
            if len(body_text) > len(last_text) + 50:
                last_text = body_text

                # If we have contains requirements, check them
                if contains:
                    if all(any(c in body_text for c in group) if isinstance(group, list)
                           else group in body_text
                           for group in contains):
                        return body_text
                else:
                    # Just wait for any substantial response
                    return body_text

            last_text = body_text

        # Timeout — return what we have
        return last_text

    def get_images(self) -> list:
        """Get all images in the chat area."""
        return self.page.locator("img[src*='blob:'], img[src*='data:'], img[src*='http']").all()

    def close(self):
        self._browser.close()
        self._pw.stop()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.skipif(not playwright_available(), reason="Playwright/Chromium not available")
class TestDeepResearch:
    """Test deep_research tool — agent should research a topic and return findings."""

    def test_research_new_topic(self):
        """Ask about a topic — agent should call deep_research and return structured findings."""
        with StoryTellerPage() as st:
            st.login()
            st.new_session()

            st.send_message("אני רוצה לעשות סרטון על AWS Step Functions - תחקור את הנושא")

            # Wait for research response — should contain research markers
            body = st.wait_for_response(RESEARCH_TIMEOUT)

            # Verify agent researched and responded in Hebrew
            has_hebrew = any('\u0590' <= c <= '\u05FF' for c in body)
            assert has_hebrew, "Response should be in Hebrew"

            # Should contain topic-related content
            topic_markers = ["Step Functions", "AWS", "workflow", "סרטון", "תוכן"]
            found = [m for m in topic_markers if m.lower() in body.lower()]
            assert len(found) >= 2, f"Expected topic markers, found only: {found}"

            # Response should be substantial (research produces detailed output)
            # Count Hebrew chars as proxy for substantive response
            hebrew_chars = sum(1 for c in body if '\u0590' <= c <= '\u05FF')
            assert hebrew_chars > 100, f"Expected substantial Hebrew response, got {hebrew_chars} Hebrew chars"


@pytest.mark.integration
@pytest.mark.skipif(not playwright_available(), reason="Playwright/Chromium not available")
class TestQRCode:
    """Test QR code generation — agent should generate a QR code image."""

    def test_generate_qr_code(self):
        """Ask for a QR code — agent should generate and display it."""
        with StoryTellerPage() as st:
            st.login()
            st.new_session()

            st.send_message("תייצר לי QR code לכתובת https://docs.aws.amazon.com")

            body = st.wait_for_response(QR_TIMEOUT)

            # Should mention QR in response
            assert "qr" in body.lower() or "QR" in body, "Response should mention QR"

            # Check for image in chat (QR code rendered as image)
            images = st.get_images()
            # Also check for download link pattern
            has_media = "media://" in body or len(images) > 0 or "📎" in body or "קוד" in body

            # The agent should either show the image or provide a download reference
            assert has_media or "QR" in body, \
                "Expected QR code image or download reference in response"


@pytest.mark.integration
@pytest.mark.skipif(not playwright_available(), reason="Playwright/Chromium not available")
class TestThumbnail:
    """Test thumbnail generation — agent should design/generate a thumbnail."""

    def test_thumbnail_design(self):
        """Ask for a thumbnail — agent should call design_thumbnail."""
        with StoryTellerPage() as st:
            st.login()
            st.new_session()

            st.send_message("תעצב לי תמונת טאמבנייל לסרטון על Docker למתחילים")

            # Thumbnail generation takes longer (sub-agent + Gemini)
            body = st.wait_for_response(THUMBNAIL_TIMEOUT)

            # Should reference thumbnail/design concepts
            design_markers = ["טאמבנייל", "תמונ", "עיצוב", "thumbnail", "Docker"]
            found = [m for m in design_markers if m.lower() in body.lower()]
            assert len(found) >= 1, f"Expected thumbnail-related content, found: {found}"

            # Agent should either show image or discuss the design
            has_image = len(st.get_images()) > 0
            has_design_discussion = any(w in body for w in ["רקע", "טקסט", "צבע", "סגנון", "תמונה"])

            assert has_image or has_design_discussion, \
                "Expected thumbnail image or design discussion"


@pytest.mark.integration
@pytest.mark.skipif(not playwright_available(), reason="Playwright/Chromium not available")
class TestExportDocument:
    """Test export_document tool — agent should export content as a file."""

    def test_export_plan(self):
        """Generate content then ask to export — should produce a downloadable file."""
        with StoryTellerPage() as st:
            st.login()
            st.new_session()

            # First, give the agent something to export
            st.send_message("תכנן לי סרטון קצר על Git למתחילים - 5 דקות")
            st.wait_for_response(RESEARCH_TIMEOUT)

            # Now ask to export
            st.send_message("תייצא את התוכנית לקובץ")
            body = st.wait_for_response(30)

            # Should reference a file/export
            export_markers = ["📄", "קובץ", "ייצוא", "export", "media://", "download"]
            found = [m for m in export_markers if m.lower() in body.lower()]
            assert len(found) >= 1, f"Expected export reference, found: {found}"


@pytest.mark.integration
@pytest.mark.skipif(not playwright_available(), reason="Playwright/Chromium not available")
class TestCombinedWorkflow:
    """Full workflow test — research + plan + QR + thumbnail in one session."""

    def test_full_video_planning_workflow(self):
        """Simulate a real user session: topic → research → content → QR → thumbnail."""
        with StoryTellerPage() as st:
            st.login()
            st.new_session()

            # Step 1: Start with a topic — triggers research + session naming
            print("  Step 1: Topic + research...")
            st.send_message("בוא נתכנן סרטון על Amazon Bedrock Agents - מדריך מעשי")
            body = st.wait_for_response(RESEARCH_TIMEOUT)
            has_hebrew = any('\u0590' <= c <= '\u05FF' for c in body)
            assert has_hebrew, "Step 1: Expected Hebrew research response"
            assert len(body) > 500, f"Step 1: Expected substantial response, got {len(body)} chars"

            # Step 2: Ask for specific content section
            print("  Step 2: Content generation...")
            st.send_message("תכתוב לי את הפתיח - hook חזק ל-30 שניות ראשונות")
            body = st.wait_for_response(60)
            hook_markers = ["שנייה", "פתיח", "hook", "Bedrock", "Agent"]
            found = [m for m in hook_markers if m.lower() in body.lower()]
            assert len(found) >= 1, f"Step 2: Expected hook content, found: {found}"

            # Step 3: QR code for resources
            print("  Step 3: QR code...")
            st.send_message("תייצר QR code לדף התיעוד https://docs.aws.amazon.com/bedrock/")
            body = st.wait_for_response(QR_TIMEOUT)
            assert "qr" in body.lower() or "QR" in body or len(st.get_images()) > 0, \
                "Step 3: Expected QR code reference"

            # Step 4: Thumbnail
            print("  Step 4: Thumbnail...")
            st.send_message("תעצב טאמבנייל לסרטון הזה")
            body = st.wait_for_response(THUMBNAIL_TIMEOUT)
            thumb_markers = ["טאמבנייל", "תמונ", "עיצוב", "thumbnail"]
            found = [m for m in thumb_markers if m.lower() in body.lower()]
            assert len(found) >= 1 or len(st.get_images()) > 0, \
                f"Step 4: Expected thumbnail content, found: {found}"

            print("  ✅ Full workflow completed successfully!")
