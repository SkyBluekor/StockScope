import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// This test-only server has NO API proxy to a live backend or real KRX.
export default defineConfig({plugins:[react()],server:{host:"127.0.0.1",port:5279,strictPort:true,proxy:{}}});
