import { defineConfig } from "@playwright/test";

// Expects the API on :8000 (sandbox store) and `pnpm dev` or `pnpm start` on :3000.
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  use: {
    baseURL: process.env.WEB_URL ?? "http://localhost:3000",
    launchOptions: { executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" },
    screenshot: "only-on-failure",
  },
});
