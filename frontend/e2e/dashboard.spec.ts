import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("loads with the recurring payments summary visible", async ({ page }) => {
    // No RecurringPayment fixtures are seeded, so the empty state is the
    // deterministic thing to assert on -- see seed_e2e_fixtures.py.
    await expect(page.getByTestId("recurring-payments-empty-state")).toBeVisible();
  });

  test("toggles between light and dark mode", async ({ page }) => {
    // ThemeContext.tsx applies theme via document.documentElement.classList
    // ("dark" class present/absent), not a data-* attribute.
    const toggle = page.getByTestId("theme-toggle");
    await expect(toggle).toBeVisible();
    const isDark = () => page.evaluate(() => document.documentElement.classList.contains("dark"));

    const initialIsDark = await isDark();
    await toggle.click();
    expect(await isDark()).toBe(!initialIsDark);

    // Toggling back should restore the original state -- catches a toggle that
    // only ever moves one direction.
    await toggle.click();
    expect(await isDark()).toBe(initialIsDark);
  });
});
