"""End-to-end sanity test using Playwright headless browser.

Run with: uv run pytest tests/test_e2e.py -v -m integration
Requires: Chromium installed, deployed app accessible.
"""

import os
import pytest
import asyncio

def _find_chromium():
    """Find latest installed Playwright Chromium."""
    import glob
    candidates = sorted(glob.glob(os.path.expanduser(
        "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"
    )))
    return candidates[-1] if candidates else "/usr/bin/chromium-browser"


CHROMIUM = os.environ.get("CHROMIUM_PATH", _find_chromium())
APP_URL = os.environ.get("APP_URL", "https://d47e04mnn21ns.cloudfront.net")
TEST_EMAIL = os.environ.get("TEST_EMAIL", "e2e-test@storyteller.dev")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "Test6e6b80e86e571fb1!1")


def playwright_available():
    try:
        from playwright.sync_api import sync_playwright
        return os.path.exists(CHROMIUM)
    except ImportError:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not playwright_available(), reason="Playwright/Chromium not available")
class TestE2E:
    """End-to-end browser tests."""

    def _get_browser(self):
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True, executable_path=CHROMIUM)
        return pw, browser

    def test_login_page_loads(self):
        pw, browser = self._get_browser()
        try:
            page = browser.new_page()
            page.goto(APP_URL, wait_until="networkidle")

            assert page.title() == "StoryTeller — תכנון סרטוני YouTube"
            assert page.locator('input[type="email"]').is_visible()
            assert page.locator('input[type="password"]').is_visible()
            assert page.locator('button[type="submit"]').is_visible()
        finally:
            browser.close()
            pw.stop()

    def test_login_with_credentials(self):
        pw, browser = self._get_browser()
        try:
            page = browser.new_page()
            page.goto(APP_URL, wait_until="networkidle")

            page.locator('input[type="email"]').fill(TEST_EMAIL)
            page.locator('input[type="password"]').fill(TEST_PASSWORD)
            page.locator('button[type="submit"]').click()

            page.wait_for_timeout(3000)

            # Should see chat interface
            assert page.locator('text=StoryTeller').first.is_visible()
            # Welcome message should be present
            assert page.locator('text=YouTube').first.is_visible()
        finally:
            browser.close()
            pw.stop()

    def test_login_wrong_password(self):
        pw, browser = self._get_browser()
        try:
            page = browser.new_page()
            page.goto(APP_URL, wait_until="networkidle")

            page.locator('input[type="email"]').fill(TEST_EMAIL)
            page.locator('input[type="password"]').fill("WrongPass123!")
            page.locator('button[type="submit"]').click()

            page.wait_for_timeout(2000)

            # Should show error message
            error = page.locator('text=שגויים')
            assert error.is_visible() or page.locator('input[type="email"]').is_visible()
        finally:
            browser.close()
            pw.stop()

    def test_send_message_and_get_response(self):
        pw, browser = self._get_browser()
        try:
            page = browser.new_page()
            page.goto(APP_URL, wait_until="networkidle")

            # Login
            page.locator('input[type="email"]').fill(TEST_EMAIL)
            page.locator('input[type="password"]').fill(TEST_PASSWORD)
            page.locator('button[type="submit"]').click()
            page.wait_for_timeout(3000)

            # Send a message
            textarea = page.locator("textarea").first
            textarea.fill("אמור שלום בשורה אחת")
            # Use the send button (may be button with SVG icon, not type=submit)
            send_btn = page.locator('button[type="submit"], button[aria-label*="send"], button[aria-label*="שלח"]').last
            send_btn.click()

            # Wait for response (streaming — up to 30s)
            page.wait_for_timeout(25000)

            # User message should appear on page
            page_text = page.locator("body").inner_text()
            assert "שלום" in page_text

            # No raw JSON in the response
            assert '"type": "progress"' not in page_text
            assert "\\u05" not in page_text
        finally:
            browser.close()
            pw.stop()

    def test_new_chat_button(self):
        pw, browser = self._get_browser()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(APP_URL, wait_until="networkidle")

            # Login
            page.locator('input[type="email"]').fill(TEST_EMAIL)
            page.locator('input[type="password"]').fill(TEST_PASSWORD)
            page.locator('button[type="submit"]').click()
            page.wait_for_timeout(3000)

            # Click new chat button
            new_chat_btn = page.locator('button:has-text("שיחה חדשה")').first
            new_chat_btn.click(timeout=5000)
            page.wait_for_timeout(1000)

            # Should still be in chat, StoryTeller header visible
            assert page.locator('text=StoryTeller').first.is_visible()
        finally:
            browser.close()
            pw.stop()
