import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";

// Routes only to the restricted local FastAPI GET-only worker. No real app or provider proxy.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1", port: 5283, strictPort: true,
    proxy: {
      "/__p004/": {target: "http://127.0.0.1:5284", changeOrigin: false},
      "/api/holdings/": {target: "http://127.0.0.1:5284", changeOrigin: false},
    },
  },
});
