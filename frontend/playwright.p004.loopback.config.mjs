import {defineConfig} from "@playwright/test";

const systemChrome = process.env.P004_SYSTEM_CHROME?.trim();
export default defineConfig({
  testDir: "./e2e",
  testMatch: "p004-holdings-loopback.spec.mjs",
  timeout: 90000,
  retries: 0,
  workers: 1,
  reporter: [["line"]],
  use: {
    baseURL: "http://127.0.0.1:5283",
    browserName: "chromium",
    headless: true,
    ...(systemChrome
      ? {launchOptions: {executablePath: systemChrome}}
      : {channel: "chrome"}),
    // Real private operational snapshot content is in the browser.
    // Never persist screenshots, trace, video or HAR artifacts.
    trace: "off", screenshot: "off", video: "off",
  },
  webServer: {
    command: "npm run dev -- --config e2e/vite.p004.loopback.config.ts --host 127.0.0.1 --port 5283 --strictPort",
    url: "http://127.0.0.1:5283/p004-loopback.html",
    reuseExistingServer: false,
    timeout: 60000,
  },
});
