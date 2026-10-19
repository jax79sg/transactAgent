import { expect, test } from "@playwright/test";

import { E2E_USERNAME, login } from "./helpers";

test.describe("Login", () => {
  test("signs in with valid credentials and reaches the dashboard", async ({ page }) => {
    await login(page);
    // ProtectedLayout renders the NavBar once authenticated -- its logout button
    // is a reliable "we're actually in the app" signal independent of Dashboard's
    // own content, which is covered separately in dashboard.spec.ts.
    await expect(page.getByTestId("logout-button")).toBeVisible();
  });

  test("rejects an invalid password and stays on the login page", async ({ page }) => {
    await page.goto("/login");
    await page.getByTestId("login-username").fill(E2E_USERNAME);
    await page.getByTestId("login-password").fill("definitely-wrong-password");
    await page.getByTestId("login-submit").click();

    await expect(page.getByTestId("login-error")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("redirects an unauthenticated visitor away from a protected page", async ({ page }) => {
    await page.goto("/transactions");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("logs out back to the login page", async ({ page }) => {
    await login(page);
    await page.getByTestId("logout-button").click();
    await expect(page).toHaveURL(/\/login$/);
  });
});
