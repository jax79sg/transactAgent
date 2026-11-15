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

  // Issues #65-#70: the Transactions page offers the same accounts the Balances tab lists. The seed puts the five
  // fixture transactions on "E2E Savings"; "E2E Current" (savings) and "E2E Card" (a credit card) have none.
  test("offers every account in the Account filter with its type and how many transactions it has", async ({ page }) => {
    const filter = page.getByTestId("account-filter-select");
    await expect(filter.getByRole("option", { name: "E2E Savings · Savings / current · 5 transactions" })).toBeAttached();
    await expect(filter.getByRole("option", { name: "E2E Current · Savings / current · no transactions" })).toBeAttached();
    await expect(filter.getByRole("option", { name: "E2E Card · Credit card · no transactions" })).toBeAttached();
  });

  test("choosing an account lists its transactions, each naming the account and its type", async ({ page }) => {
    await page.getByTestId("account-filter-select").selectOption({ label: "E2E Savings · Savings / current · 5 transactions" });

    const row = page.getByTestId(/^transaction-row-/).filter({ hasText: "NTUC FAIRPRICE" });
    await expect(row).toBeVisible();
    await expect(row.getByTestId(/^txn-account-/)).toContainText("E2E Savings");
    await expect(row.getByTestId(/^txn-account-/)).toContainText("Savings / current");
    await expect(page.getByTestId(/^transaction-row-/)).toHaveCount(5);
  });

  test("an account with no transactions says so instead of showing a bare empty list", async ({ page }) => {
    await page.getByTestId("account-filter-select").selectOption({ label: "E2E Card · Credit card · no transactions" });

    await expect(page.getByTestId("account-has-no-transactions")).toContainText("“E2E Card” has no transactions");
    await expect(page.getByTestId(/^transaction-row-/)).toHaveCount(0);
  });
});
