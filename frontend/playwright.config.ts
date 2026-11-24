import { defineConfig, devices } from "@playwright/test";

// The smoke suite runs against the *static demonstration build* served by `vite preview`
// (base path /IncidentLens/, exactly as on GitHub Pages). Build it first: `npm run demo:data && npm run build:demo`.
const PORT = 4173;
const BASE = `http://127.0.0.1:${PORT}/IncidentLens/`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  timeout: 45_000,
  expect: { timeout: 8_000 },
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: BASE, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: `npm run preview -- --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: BASE,
    // `vite preview` re-reads vite.config.ts, so it needs the same base path the site was built with.
    env: { VITE_BASE: "/IncidentLens/" },
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
