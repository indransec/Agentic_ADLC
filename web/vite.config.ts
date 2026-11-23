// The browser application (feature 022). In development Vite serves it on :5173 and forwards
// /api and /config.json to adlc-web, which forwards /api to the platform API (research R-13).
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const uiPort = process.env["ADLC_UI_PORT"] ?? "8501";
const target = `http://127.0.0.1:${uiPort}`;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target, changeOrigin: false },
      "/config.json": { target, changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    assetsDir: "assets",
    sourcemap: false,
  },
});
