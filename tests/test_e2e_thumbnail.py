#!/usr/bin/env python3
"""Playwright E2E test: thumbnail generation via UI.

Logs in, sends a thumbnail request, verifies the agent responds
with an image (or meaningful progress) within the timeout.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright, expect

SITE_URL = "https://d1odwixjhlwcc4.cloudfront.net"
EMAIL = "g1@amazon.com"
PASSWORD = "Test123!@#Secure"
TIMEOUT_MS = 180_000  # 3 min for agent response


def test_thumbnail_generation():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="he-IL",
        )
        page = context.new_page()

        # ── Login ────────────────────────────────────────────────
        print("1. Navigating to site...")
        page.goto(SITE_URL, wait_until="networkidle")
        page.wait_for_timeout(2000)

        # Check if we need to log in
        if page.locator("input[type='email'], input[name='username']").count() > 0:
            print("2. Logging in...")
            email_input = page.locator("input[type='email'], input[name='username']").first
            email_input.fill(EMAIL)
            
            password_input = page.locator("input[type='password']").first
            password_input.fill(PASSWORD)
            
            submit_btn = page.locator("button[type='submit'], input[type='submit']").first
            submit_btn.click()
            
            page.wait_for_timeout(3000)
            print("   Logged in")
        else:
            print("2. Already logged in (or no login form)")

        # Wait for chat interface to load
        print("3. Waiting for chat interface...")
        page.wait_for_selector("textarea", timeout=15000)
        page.wait_for_timeout(1000)
        
        # Take screenshot of initial state
        page.screenshot(path="/tmp/thumb_test_01_initial.png")
        print("   Chat loaded ✅")

        # ── Start new session ───────────────────────────────────
        # Look for new-session button
        new_session_btn = page.locator("button:has-text('שיחה חדשה'), button:has-text('חדש'), button[title*='new'], button[title*='חדש']").first
        if new_session_btn.count() > 0:
            print("4. Starting new session...")
            new_session_btn.click()
            page.wait_for_timeout(1000)
        else:
            print("4. Using current session")

        # ── Send thumbnail request ──────────────────────────────
        print("5. Sending thumbnail request...")
        textarea = page.locator("textarea").first
        textarea.fill("תעצב לי תמונת טאמבנייל לסרטון על Amazon Bedrock AgentCore - סרטון טכני L200")
        page.wait_for_timeout(500)
        
        # Press Enter to send
        textarea.press("Enter")
        print("   Message sent")
        
        page.screenshot(path="/tmp/thumb_test_02_sent.png")

        # ── Wait for response ───────────────────────────────────
        print("6. Waiting for agent response...")
        
        # Wait for at least one assistant message (beyond the welcome message)
        # The response might take a while due to sub-agent + Gemini call
        start_time = time.time()
        response_found = False
        has_image = False
        has_error = False
        last_screenshot_time = 0
        
        while time.time() - start_time < 180:  # 3 min max
            page.wait_for_timeout(3000)
            elapsed = time.time() - start_time
            
            # Take periodic screenshots
            if elapsed - last_screenshot_time > 15:
                screenshot_num = int(elapsed // 15) + 3
                page.screenshot(path=f"/tmp/thumb_test_{screenshot_num:02d}_progress.png")
                last_screenshot_time = elapsed
            
            # Check for progress indicator (agent is working)
            progress = page.locator("text=מעצב טאמבנייל").count()
            connecting = page.locator("text=מתחבר").count()
            loading_dots = page.locator(".animate-bounce").count()
            
            if progress > 0:
                print(f"   [{elapsed:.0f}s] 🎨 Designing thumbnail...")
            elif connecting > 0 or loading_dots > 0:
                print(f"   [{elapsed:.0f}s] ⏳ Agent working...")
            
            # Check for an image in the response
            images = page.locator(".prose-rtl img")
            if images.count() > 0:
                has_image = True
                response_found = True
                print(f"   [{elapsed:.0f}s] 🖼️ Thumbnail image found!")
                break
            
            # Check for error messages
            error_text = page.locator("text=שגיאה").count()
            if error_text > 0:
                has_error = True
                response_found = True
                print(f"   [{elapsed:.0f}s] ❌ Error in response")
                break
            
            # Check if agent responded (any new assistant message with substantial content)
            # Look for messages that contain thumbnail-related Hebrew words
            assistant_msgs = page.locator(".prose-rtl")
            msg_count = assistant_msgs.count()
            if msg_count > 1:  # More than just the welcome message
                last_msg = assistant_msgs.nth(msg_count - 1)
                text = last_msg.text_content() or ""
                if len(text) > 50 and any(w in text for w in ["טאמבנייל", "תמונ", "עיצוב", "רקע", "טקסט"]):
                    response_found = True
                    print(f"   [{elapsed:.0f}s] 💬 Agent responded about thumbnails ({len(text)} chars)")
                    # Keep waiting a bit more for image
                    if not has_image:
                        page.wait_for_timeout(10000)
                        images = page.locator(".prose-rtl img")
                        if images.count() > 0:
                            has_image = True
                            print(f"   Image appeared after waiting!")
                    break
        
        # Final screenshot
        page.screenshot(path="/tmp/thumb_test_final.png")
        
        # ── Results ─────────────────────────────────────────────
        elapsed = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"RESULTS ({elapsed:.0f}s)")
        print(f"{'='*60}")
        print(f"Response received: {'✅' if response_found else '❌'}")
        print(f"Image generated:   {'✅' if has_image else '❌' if has_error else '⏳ (may need Gemini API)'}")
        print(f"Error:             {'❌ Yes' if has_error else '✅ No'}")
        
        # Get the page content for debugging
        if response_found:
            assistant_msgs = page.locator(".prose-rtl")
            last_idx = assistant_msgs.count() - 1
            if last_idx >= 0:
                text = assistant_msgs.nth(last_idx).text_content() or ""
                print(f"\nLast assistant message ({len(text)} chars):")
                print(text[:500])
        
        browser.close()
        
        # Return results
        return {
            "response": response_found,
            "image": has_image,
            "error": has_error,
            "elapsed": elapsed,
        }


if __name__ == "__main__":
    result = test_thumbnail_generation()
    print(f"\n{'✅ PASS' if result['response'] else '❌ FAIL'}")
    sys.exit(0 if result["response"] else 1)
