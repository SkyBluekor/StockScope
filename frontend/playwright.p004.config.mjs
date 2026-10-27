import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "p004-holdings-panel.spec.mjs",
  timeout: 45000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:5281",
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run dev -- --config e2e/vite.p004.config.ts --host 127.0.0.1 --port 5281 --strictPort",
    url: "http://127.0.0.1:5281/p004-test.html",
    reuseExistingServer: false,
    timeout: 60000,
  },
});
