import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// P0-04 browser-test-only server. No production API proxy or provider calls.
export default defineConfig({
  plugins: [react()],
  server: {host: "127.0.0.1", port: 5281, strictPort: true, proxy: {}},
});
