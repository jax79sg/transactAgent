import { defineConfig, devices } from "@playwright/test";

// Runs against an already-running stack (docker-compose in CI, or your own local
// `docker compose up`) -- no webServer block here, deliberately: this suite tests
// the real built app, not a vite dev server, and the nightly CI workflow is
// responsible for bringing the stack up/down around it.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:8787",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
