/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = process.env.VITE_DEV_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  // GitHub Pages serves the site from /<repo>/; the static-demo build sets VITE_BASE accordingly.
  base: process.env.VITE_BASE ?? "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: backend, changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: false,
  },
});
