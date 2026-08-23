import type { Page } from "@playwright/test";

// The e2e_test user is created by database/src/transactagent_db/seed_e2e_fixtures.py
// against the CI-only docker-compose stack -- never a real deployment.
export const E2E_USERNAME = "e2e_test";
export const E2E_PASSWORD = "E2e-Test-Password-2026";

/**
 * AuthContext stores the session token in sessionStorage (not a cookie/localStorage),
 * which Playwright's storageState can't persist across test files -- so every spec
 * logs in fresh via the real UI rather than trying to short-circuit auth.
 */
export async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByTestId("login-username").fill(E2E_USERNAME);
  await page.getByTestId("login-password").fill(E2E_PASSWORD);
  await page.getByTestId("login-submit").click();
  await page.waitForURL("/");
}
