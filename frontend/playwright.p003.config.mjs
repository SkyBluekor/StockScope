import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir:"./e2e",
  testMatch:"p003-scanner-recheck.spec.mjs",
  timeout:45000,
  retries:0,
  workers:1,
  use:{baseURL:"http://127.0.0.1:5279",browserName:"chromium",headless:true,
    trace:"retain-on-failure",screenshot:"only-on-failure"},
  webServer:{command:"npm run dev -- --config e2e/vite.p003.config.ts --host 127.0.0.1 --port 5279 --strictPort",
    url:"http://127.0.0.1:5279/scanner",reuseExistingServer:false,timeout:60000},
});
