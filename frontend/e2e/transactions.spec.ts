import { expect, test } from "@playwright/test";

import { login } from "./helpers";

// Fixture data comes from database/src/transactagent_db/seed_e2e_fixtures.py.
test.describe("Transactions", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/transactions");
  });

  test("lists the seeded fixture transactions", async ({ page }) => {
    await expect(page.getByText("NTUC FAIRPRICE")).toBeVisible();
    await expect(page.getByText("GRAB TRANSPORT")).toBeVisible();
    await expect(page.getByText("SALARY")).toBeVisible();
  });

  test("filters the list via the search box", async ({ page }) => {
    await page.getByTestId("text-search-input").fill("NTUC");

    await expect(page.getByText("NTUC FAIRPRICE")).toBeVisible();
    await expect(page.getByText("GRAB TRANSPORT")).not.toBeVisible();
  });
});
