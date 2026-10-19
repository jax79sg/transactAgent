import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test.describe("Settings", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/settings");
  });

  test("loads with the Google Drive connect control visible", async ({ page }) => {
    await expect(page.getByTestId("connect-drive-button")).toBeVisible();
  });

  test("adds a new category", async ({ page }) => {
    const categoryName = `E2E Category ${Date.now()}`;
    await page.getByTestId("new-category-input").fill(categoryName);
    await page.getByRole("button", { name: "Add" }).click();

    await expect(page.getByText(categoryName)).toBeVisible();
  });
});
