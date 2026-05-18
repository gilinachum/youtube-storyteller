import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: '**/*.mjs',
  timeout: 180000,
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
  },
});
