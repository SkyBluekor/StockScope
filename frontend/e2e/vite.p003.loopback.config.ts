import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Strictly loopback. Only Scanner endpoint calls proxy to the dedicated
// safe FastAPI application. All other browser API calls are Playwright-mocked.
export default defineConfig({
  plugins:[react()],
  server:{
    host:"127.0.0.1",port:5279,strictPort:true,
    proxy:{
      "/api/backtest/scanner":{target:"http://127.0.0.1:5280",changeOrigin:false},
      "/api/backtest/jobs/":{target:"http://127.0.0.1:5280",changeOrigin:false},
    },
  },
});
