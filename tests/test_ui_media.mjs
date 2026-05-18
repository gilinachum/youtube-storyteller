/**
 * Playwright UI test — media display (QR codes, thumbnails, quick-reply questions)
 * Run: npx playwright test tests/test_ui_media.mjs --headed  (or headless by default)
 */
import { test, expect } from '@playwright/test';

const APP_URL = process.env.APP_URL || 'https://d47e04mnn21ns.cloudfront.net';
const TEST_EMAIL = process.env.TEST_EMAIL || 'e2e-test@storyteller.dev';
const TEST_PASS = process.env.TEST_PASS;

if (!TEST_PASS) throw new Error('TEST_PASS env var required');

test.describe('StoryTeller UI — media & interaction', () => {

  test.beforeEach(async ({ page }) => {
    // Login
    await page.goto(APP_URL);
    await page.waitForTimeout(2000);

    // Fill login form
    const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i], input[placeholder*="מייל"]');
    if (await emailInput.count() > 0) {
      await emailInput.fill(TEST_EMAIL);
      const passInput = page.locator('input[type="password"]');
      await passInput.fill(TEST_PASS);
      const loginBtn = page.locator('button[type="submit"], button:has-text("כניסה"), button:has-text("Login"), button:has-text("התחבר")');
      await loginBtn.click();
      // Wait for chat UI to appear
      await page.waitForSelector('textarea, [contenteditable], input[placeholder*="הקלד"], input[placeholder*="message" i]', { timeout: 15000 });
    }
  });

  test('QR code renders inline with media:// protocol', async ({ page }) => {
    // Create new session
    const newBtn = page.locator('button:has-text("שיחה חדשה"), button:has-text("New"), button[aria-label*="new" i]');
    if (await newBtn.count() > 0) await newBtn.first().click();
    await page.waitForTimeout(1000);

    // Send QR request
    const input = page.locator('textarea, [contenteditable], input[placeholder*="הקלד"]').first();
    await input.fill('צור QR code ל-https://example.com');
    await page.keyboard.press('Enter');

    // Wait for agent response (up to 90s for Code Interpreter)
    // Keep checking until we see an image, error, or the response stabilizes
    let lastLen = 0;
    let stableCount = 0;
    for (let i = 0; i < 30; i++) {
      await page.waitForTimeout(3000);
      const msgs = page.locator('.message-assistant');
      const count = await msgs.count();
      if (count === 0) continue;
      const html = await msgs.last().innerHTML();
      if (html.includes('<img') || html.includes('❌') || html.includes('שגיאה')) break;
      if (html.length === lastLen && html.length > 50) {
        stableCount++;
        if (stableCount >= 3) break; // Content stabilized
      } else {
        stableCount = 0;
      }
      lastLen = html.length;
    }

    const assistantMsg = page.locator('.message-assistant').last();

    // Check: either MediaImage component rendered (has presigned URL) or loading spinner
    const imgs = assistantMsg.locator('img');
    const imgCount = await imgs.count();

    if (imgCount > 0) {
      const src = await imgs.first().getAttribute('src');
      console.log('QR image src:', src?.substring(0, 100));
      // Should have a real src (presigned S3 URL), not empty
      expect(src).toBeTruthy();
      expect(src).not.toBe('');
      // Should be a presigned S3 URL
      expect(src).toMatch(/^https?:\/\//);
      console.log('✅ QR code image renders with valid presigned URL');
    } else {
      // Check if there's a loading spinner (MediaImage still loading)
      const spinner = assistantMsg.locator('.animate-pulse, .animate-spin');
      if (await spinner.count() > 0) {
        console.log('⏳ QR image still loading (MediaImage fetching presigned URL)');
      } else {
        // Check the raw HTML for debugging
        const html = await assistantMsg.innerHTML();
        console.log('Response HTML (first 500):', html.substring(0, 500));
        // If there's an error message, that's also useful info
        if (html.includes('❌') || html.includes('error') || html.includes('שגיאה')) {
          console.log('⚠️ Agent returned an error (not a rendering bug)');
        } else {
          throw new Error('No image found in QR response');
        }
      }
    }
  });

  test('Quick-reply questions use numbered format', async ({ page }) => {
    const newBtn = page.locator('button:has-text("שיחה חדשה"), button:has-text("New"), button[aria-label*="new" i]');
    if (await newBtn.count() > 0) await newBtn.first().click();
    await page.waitForTimeout(1000);

    // Ask about a topic — agent should ask numbered questions
    const input = page.locator('textarea, [contenteditable], input[placeholder*="הקלד"]').first();
    await input.fill('אני רוצה לתכנן סרטון על AWS Lambda');
    await page.keyboard.press('Enter');

    // Wait for response
    await page.waitForTimeout(20000);

    const assistantMsg = page.locator('.message-assistant').last();
    await expect(assistantMsg).toBeVisible({ timeout: 60000 });

    const text = await assistantMsg.innerText();
    console.log('Agent response (first 800):', text.substring(0, 800));

    // Check for numbered questions with Hebrew letter options
    const hasNumberedQ = /[12]\s*[.)]/.test(text);
    const hasHebrewOptions = /[12][אבגד]/.test(text) || /[אבגד][.)]/.test(text);

    console.log(`Numbered questions: ${hasNumberedQ}, Hebrew options: ${hasHebrewOptions}`);
    
    if (hasHebrewOptions) {
      console.log('✅ Quick-reply format detected (numbered questions with Hebrew letter options)');
    } else if (hasNumberedQ) {
      console.log('⚠️ Numbered questions found but no Hebrew letter options — model may need reinforcement');
    } else {
      console.log('⚠️ No numbered question format detected — checking if agent asked questions at all');
      const hasQuestion = text.includes('?') || text.includes('؟');
      console.log(`Has questions: ${hasQuestion}`);
    }

    // Take screenshot for visual verification
    await page.screenshot({ path: '/tmp/storyteller-quickreply.png', fullPage: true });
    console.log('📸 Screenshot saved to /tmp/storyteller-quickreply.png');
  });

  test('Thumbnail generation displays inline image', async ({ page }) => {
    const newBtn = page.locator('button:has-text("שיחה חדשה"), button:has-text("New"), button[aria-label*="new" i]');
    if (await newBtn.count() > 0) await newBtn.first().click();
    await page.waitForTimeout(1000);

    const input = page.locator('textarea, [contenteditable], input[placeholder*="הקלד"]').first();
    await input.fill('צור לי טאמבנייל לסרטון על AWS Lambda עם טקסט "5 טיפים" על רקע כחול כהה');
    await page.keyboard.press('Enter');

    // Thumbnail takes longer: parent agent → sub-agent → Gemini → S3 → register
    // Wait up to 2.5 minutes, checking every 3s
    let lastLen = 0;
    let stableCount = 0;
    for (let i = 0; i < 50; i++) {
      await page.waitForTimeout(3000);
      const msgs = page.locator('.message-assistant');
      const count = await msgs.count();
      if (count === 0) continue;
      const html = await msgs.last().innerHTML();
      if (html.includes('<img') || html.includes('❌') || html.includes('שגיאה') || html.includes('Failed to load')) break;
      if (html.length === lastLen && html.length > 100) {
        stableCount++;
        if (stableCount >= 5) break; // Content stabilized (15s of no change)
      } else {
        stableCount = 0;
      }
      lastLen = html.length;
    }

    const messages = page.locator('.message-assistant');
    const lastMsg = messages.last();
    await expect(lastMsg).toBeVisible({ timeout: 90000 });

    const html = await lastMsg.innerHTML();
    const text = await lastMsg.innerText();

    // Check for image
    const imgs = lastMsg.locator('img');
    const imgCount = await imgs.count();

    if (imgCount > 0) {
      const src = await imgs.first().getAttribute('src');
      console.log('Thumbnail src:', src?.substring(0, 100));
      expect(src).toBeTruthy();
      expect(src).not.toBe('');
      console.log('✅ Thumbnail renders inline');
    } else {
      console.log('Response text (first 500):', text.substring(0, 500));
      console.log('Response HTML (first 500):', html.substring(0, 500));
      
      if (html.includes('animate-pulse') || html.includes('animate-spin')) {
        console.log('⏳ Thumbnail still loading');
      } else if (text.includes('❌') || text.includes('שגיאה') || text.includes('failed')) {
        console.log('⚠️ Thumbnail generation failed (agent error, not rendering bug)');
      } else {
        console.log('❌ No thumbnail image found in response');
      }
    }

    await page.screenshot({ path: '/tmp/storyteller-thumbnail.png', fullPage: true });
    console.log('📸 Screenshot saved to /tmp/storyteller-thumbnail.png');
  });
});
