import { defineConfig } from "@playwright/test";

// Windows UAT uses the user's already-installed Google Chrome, never the
// Playwright-managed Chromium download. An explicit executable path supports
// custom Chrome installations. Isolated CI fixture tests use a separate config.
const systemChrome = process.env.P003_CHROME_EXECUTABLE?.trim();
export default defineConfig({
  testDir: "./e2e",
  testMatch: "p003-loopback-real-server.spec.mjs",
  retries: 0,
  workers: 1,
  timeout: 240000,
  use: {
    baseURL: "http://127.0.0.1:5279",
    browserName: "chromium",
    headless: true,
    ...(systemChrome
      ? { launchOptions: { executablePath: systemChrome } }
      : { channel: "chrome" }),
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run dev -- --config e2e/vite.p003.loopback.config.ts --host 127.0.0.1 --port 5279 --strictPort",
    url: "http://127.0.0.1:5279/scanner",
    reuseExistingServer: false,
    timeout: 60000,
  },
});
