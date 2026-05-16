import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for The Tribunal CRM frontend.
 *
 * `baseURL` is taken from the PLAYWRIGHT_BASE_URL environment variable so that
 * the same suite can run against a local dev server, a Vercel preview, or a
 * Railway staging environment without code changes. The default mirrors the
 * Next.js dev server port (`npm run dev`).
 *
 * See https://playwright.dev/docs/test-configuration.
 */
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const isCI = !!process.env.CI;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers: isCI ? 1 : undefined,
  reporter: isCI ? [["github"], ["html", { open: "never" }]] : "list",

  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  /**
   * When PLAYWRIGHT_BASE_URL is set we assume the dev server is already
   * running (or we are pointing at a remote environment) and skip booting
   * `next dev` ourselves.
   */
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: "npm run dev",
        url: baseURL,
        reuseExistingServer: !isCI,
        timeout: 120_000,
        stdout: "pipe",
        stderr: "pipe",
      },
});
