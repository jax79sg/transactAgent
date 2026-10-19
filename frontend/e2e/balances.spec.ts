import { expect, test } from "@playwright/test";

import { login } from "./helpers";

// Epic 13: the Balances tab against the seeded stack. database/src/transactagent_db/seed_e2e_fixtures.py creates
// "E2E Savings" and "E2E Current" (deposit accounts with no balance entered) and "E2E Card" (a credit card), and puts
// the five fixture transactions on "E2E Savings". Serial: the cases build on one another, and the suite otherwise runs
// in parallel. Accounts are found by their visible name (their ids are generated), and every case is safe to run
// again on a database that already has the balance (it then replaces it).
test.describe.configure({ mode: "serial" });

test.describe("Dashboard balances", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  const row = (page: import("@playwright/test").Page, name: string) =>
    page.getByTestId("accounts-section").getByTestId(/^account-row-/).filter({ hasText: name });

  async function openBalances(page: import("@playwright/test").Page) {
    await page.getByTestId("dashboard-tab-balances").click();
    await expect(page.getByTestId("balances-tab")).toBeVisible();
  }

  test("the Dashboard still opens on Category Trends, and Balances lists the deposit accounts, not the card", async ({ page }) => {
    await expect(page.getByRole("tab", { name: "Category Trends" })).toHaveAttribute("aria-selected", "true");
    await openBalances(page);

    const table = page.getByTestId("balances-table");
    await expect(table).toBeVisible();
    await expect(table.getByTestId(/^balance-row-/).filter({ hasText: "E2E Savings" })).toBeVisible();
    const current = table.getByTestId(/^balance-row-/).filter({ hasText: "E2E Current" });
    await expect(current).toContainText("Anchor required");
    await expect(table).not.toContainText("E2E Card");

    // the credit card is in the accounts list, with no balance action
    await expect(row(page, "E2E Card")).toContainText("Credit card");
    await expect(row(page, "E2E Card").getByRole("button", { name: /(Set|Replace) balance/ })).toHaveCount(0);
  });

  test("the lookup says which day it is for and how far the transactions go", async ({ page }) => {
    await openBalances(page);
    await expect(page.getByTestId("lookup-heading")).toContainText("Balances at the end of");
    await expect(page.getByTestId("ingested-through")).toContainText("Transactions are ingested through");
  });

  test("entering a balance shows the figure, the total, and who is left out of it", async ({ page }) => {
    await openBalances(page);
    await row(page, "E2E Savings").getByRole("button", { name: /(Set|Replace) balance/ }).click();

    const dialog = page.getByTestId("balance-dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByTestId("balance-input").fill("1000.00");
    await dialog.getByTestId("balance-save").click();
    await expect(dialog).toBeHidden();

    await expect(page.getByTestId("account-status-message")).toContainText("E2E Savings");
    await expect(page.getByTestId("account-status-message")).toContainText("1,000.00");
    await expect(page.getByTestId("balances-table").getByTestId(/^balance-row-/).filter({ hasText: "E2E Savings" })).toContainText("1,000.00");
    await expect(page.getByTestId("combined-total")).toContainText("SGD 1,000.00");
    await expect(page.getByTestId("combined-exclusions")).toContainText("E2E Current (anchor required)");
  });

  test("the chart draws once an account has a balance", async ({ page }) => {
    await openBalances(page);
    await expect(page.getByTestId("balance-chart")).toBeVisible();
    await expect(page.getByTestId("series-summary")).toContainText("Combined balance");
    await expect(page.getByTestId("series-chart").locator("canvas")).toBeVisible();
  });

  test("renaming an account shows the new name everywhere, and renaming it back restores it", async ({ page }) => {
    await openBalances(page);
    await row(page, "E2E Current").getByRole("button", { name: "Rename" }).click();
    await page.getByTestId("rename-input").fill("E2E Everyday");
    await page.getByTestId("rename-save").click();
    await expect(page.getByTestId("rename-dialog")).toBeHidden();

    await expect(row(page, "E2E Everyday")).toBeVisible();
    await expect(page.getByTestId("balances-table")).toContainText("E2E Everyday");
    await expect(page.getByTestId("account-status-message")).toContainText("Renamed");

    await row(page, "E2E Everyday").getByRole("button", { name: "Rename" }).click();
    await page.getByTestId("rename-input").fill("E2E Current");
    await page.getByTestId("rename-save").click();
    await expect(page.getByTestId("rename-dialog")).toBeHidden();
    await expect(row(page, "E2E Current")).toBeVisible();
  });
});

test.describe("Dashboard balances on a phone", () => {
  test.use({ viewport: { width: 375, height: 800 } });

  test("the Balances tab fits the screen: the page itself does not scroll sideways", async ({ page }) => {
    await login(page);
    await page.getByTestId("dashboard-tab-balances").click();
    await expect(page.getByTestId("balances-table")).toBeVisible();
    await expect(page.getByTestId("accounts-section")).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
