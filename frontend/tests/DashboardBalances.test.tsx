import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import * as accountsApi from "../src/api/accounts";
import * as balancesApi from "../src/api/balances";
import * as dashboardsApi from "../src/api/dashboards";
import * as recurringApi from "../src/api/recurringPayments";
import { ThemeProvider } from "../src/context/ThemeContext";
import { DashboardPage } from "../src/pages/DashboardPage";
import { renderWithQueryClient } from "./balanceTestUtils";
import { accountsListFixture, balancesDateFixture, discrepanciesFixture, seriesDayFixture } from "./balancesFixtures";

vi.mock("react-chartjs-2", () => ({ Bar: () => <canvas />, Line: () => <canvas /> }));
vi.mock("../src/api/accounts");
vi.mock("../src/api/balances");
vi.mock("../src/api/dashboards");
vi.mock("../src/api/recurringPayments");

// Epic 13: the Dashboard gains a fifth tab. The existing Dashboard tests are untouched; this file covers only what
// changed: the tab, that the page still opens where it did, and the From/To box that belongs to the older charts.
function setup() {
  const none = { series: [], disclosure: { approximateCount: 0, excludedCount: 0 } };
  vi.mocked(dashboardsApi.getCategoryTrends).mockResolvedValue(none as never);
  vi.mocked(dashboardsApi.getCashFlow).mockResolvedValue(none as never);
  vi.mocked(dashboardsApi.getBankBreakdown).mockResolvedValue(none as never);
  vi.mocked(recurringApi.listRecurringPayments).mockResolvedValue([]);
  vi.mocked(recurringApi.listPendingMatches).mockResolvedValue([]);
  vi.mocked(recurringApi.listDetectionSuggestions).mockResolvedValue([]);
  vi.mocked(accountsApi.listAccounts).mockResolvedValue(accountsListFixture());
  vi.mocked(balancesApi.getBalances).mockResolvedValue(balancesDateFixture());
  vi.mocked(balancesApi.getBalanceSeries).mockResolvedValue(seriesDayFixture());
  vi.mocked(balancesApi.getDiscrepancies).mockResolvedValue(discrepanciesFixture());
  return renderWithQueryClient(
    <ThemeProvider>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("DashboardPage: the Balances tab", () => {
  it("has five tabs, Balances last, and still opens on Category Trends", () => {
    setup();
    const tabs = within(screen.getByRole("tablist")).getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Category Trends", "Cash Flow", "Bank Breakdown", "Recurring Payments", "Balances"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("dashboard-tab-balances")).toHaveAttribute("aria-selected", "false");
    expect(screen.queryByTestId("balances-tab")).not.toBeInTheDocument();
    expect(balancesApi.getBalances).not.toHaveBeenCalled(); // nothing balance-related is fetched until the tab is opened
  });

  it("shows the From/To box on the older tabs and hides it on Balances, which has its own dates", async () => {
    setup();
    const user = userEvent.setup();
    // the page's own box: date inputs that are not inside the Balances tab
    const pageDateInputs = () =>
      Array.from(document.querySelectorAll('input[type="date"]')).filter((input) => !input.closest('[data-testid="balances-tab"]'));
    expect(pageDateInputs()).toHaveLength(2);

    await user.click(screen.getByTestId("dashboard-tab-balances"));
    expect(await screen.findByTestId("balances-tab")).toBeInTheDocument();
    expect(pageDateInputs()).toHaveLength(0);
    // the chart's own From/To are inside the tab
    expect(within(screen.getByTestId("balance-chart")).getByTestId("series-from")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Cash Flow" }));
    expect(pageDateInputs()).toHaveLength(2);
    expect(screen.queryByTestId("balances-tab")).not.toBeInTheDocument();
  });

  it("leaves the Recurring Payments tab working as before", async () => {
    setup();
    await userEvent.setup().click(screen.getByRole("tab", { name: "Recurring Payments" }));
    expect(await screen.findByTestId("recurring-payments-empty-state")).toBeInTheDocument();
    expect(screen.getByText("From")).toBeInTheDocument();
  });

  it("scrolls the tab strip sideways instead of wrapping, so five tabs fit a phone", () => {
    setup();
    const list = screen.getByRole("tablist");
    expect(list.className).toContain("overflow-x-auto");
    for (const tab of within(list).getAllByRole("tab")) {
      expect(tab.className).toContain("whitespace-nowrap");
      expect(tab.className).toContain("shrink-0");
    }
  });
});
