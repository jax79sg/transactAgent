import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import * as accountsApi from "../src/api/accounts";
import * as balancesApi from "../src/api/balances";
import { ApiError } from "../src/api/client";
import type { AccountDTO, BalancesResponse } from "../src/api/types";
import { BalancesTab } from "../src/components/balances/BalancesTab";
import { ThemeProvider } from "../src/context/ThemeContext";
import { renderWithQueryClient } from "./balanceTestUtils";
import {
  accountsListFixture,
  anchorCreatedFixture,
  balancesDateFixture,
  discrepanciesFixture,
  FIXTURE_ACCOUNT_IDS,
  seriesDayFixture,
} from "./balancesFixtures";

vi.mock("react-chartjs-2", () => ({ Line: () => <canvas data-testid="line-canvas" /> }));
vi.mock("../src/api/accounts");
vi.mock("../src/api/balances");

const { fresh, main } = FIXTURE_ACCOUNT_IDS;

function mockReads(accounts: AccountDTO[] = accountsListFixture().items, balances: () => BalancesResponse = balancesDateFixture) {
  vi.mocked(accountsApi.listAccounts).mockImplementation(async () => ({ items: accounts }));
  vi.mocked(balancesApi.getBalances).mockImplementation(async () => balances());
  vi.mocked(balancesApi.getBalanceSeries).mockImplementation(async () => seriesDayFixture());
  vi.mocked(balancesApi.getDiscrepancies).mockImplementation(async () => discrepanciesFixture());
}

function setup() {
  return renderWithQueryClient(
    <ThemeProvider>
      <MemoryRouter>
        <BalancesTab />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("BalancesTab: opening", () => {
  it("starts all four reads and shows each part", async () => {
    mockReads();
    setup();
    expect(await screen.findByTestId("balances-table")).toBeInTheDocument();
    expect(await screen.findByTestId("series-chart")).toBeInTheDocument();
    expect(await screen.findByTestId("discrepancy-summary")).toBeInTheDocument();
    expect(await screen.findByTestId(`account-row-${main}`)).toBeInTheDocument();
    expect(accountsApi.listAccounts).toHaveBeenCalled();
    expect(balancesApi.getBalances).toHaveBeenCalled();
    expect(balancesApi.getBalanceSeries).toHaveBeenCalled();
    expect(balancesApi.getDiscrepancies).toHaveBeenCalled();
  });

  it("puts the warnings line first, then the lookup, the chart and the accounts", async () => {
    mockReads();
    setup();
    await screen.findByTestId(`account-row-${main}`);
    const order = ["discrepancy-summary", "balance-lookup", "balance-chart", "accounts-section"].map((id) => screen.getByTestId(id));
    for (let i = 0; i < order.length - 1; i += 1) {
      expect(order[i].compareDocumentPosition(order[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it.each([
    ["the lookup", () => vi.mocked(balancesApi.getBalances), "balances-error"],
    ["the chart", () => vi.mocked(balancesApi.getBalanceSeries), "series-error"],
    ["the warnings", () => vi.mocked(balancesApi.getDiscrepancies), "discrepancy-error"],
    ["the account list", () => vi.mocked(accountsApi.listAccounts), "accounts-error"],
  ])("a failure in %s does not blank the other parts", async (_name, failing, errorId) => {
    mockReads();
    failing().mockRejectedValue(new ApiError(500, { error: "unknown", message: "x" }));
    setup();
    expect(await screen.findByTestId(errorId)).toBeInTheDocument();
    const stillThere = {
      "balances-error": ["series-chart", "discrepancy-summary", `account-row-${main}`],
      "series-error": ["balances-table", "discrepancy-summary", `account-row-${main}`],
      "discrepancy-error": ["balances-table", "series-chart", `account-row-${main}`],
      "accounts-error": ["balances-table", "series-chart", "discrepancy-summary"],
    }[errorId] as string[];
    for (const testId of stillThere) expect(await screen.findByTestId(testId)).toBeInTheDocument();
  });
});

describe("BalancesTab: entering a balance from the prompt", () => {
  it("opens the dialog on the API's today, saves, and refreshes the table, chart, warnings and list together", async () => {
    let saved = false;
    const after = balancesDateFixture();
    Object.assign(after.accounts.find((a) => a.accountId === fresh)!, {
      status: "ok",
      balanceNative: "250.00",
      balanceSgd: "250.00",
      basis: { source: "anchor", date: "2026-10-18", statementId: null },
    });
    after.combinedTotalSgd = "2130.00";
    after.combinedIncludesCount = 3;
    after.excluded = after.excluded.filter((e) => e.accountId !== fresh);
    mockReads(undefined, () => (saved ? after : balancesDateFixture()));
    vi.mocked(accountsApi.setAnchor).mockImplementation(async () => {
      saved = true;
      return anchorCreatedFixture();
    });
    setup();
    const user = userEvent.setup();

    await user.click(await screen.findByTestId(`set-balance-${fresh}`));

    expect(screen.getByTestId("balance-dialog")).toHaveTextContent("Set the balance of “Fresh”");
    expect(screen.getByTestId("balance-date-input")).toHaveValue("2026-10-18"); // the API's today
    expect(screen.getByTestId("balance-date-input")).toHaveAttribute("max", "2026-10-18");
    await user.type(screen.getByTestId("balance-input"), "250");
    await user.click(screen.getByTestId("balance-save"));

    await waitFor(() => expect(screen.queryByTestId("balance-dialog")).not.toBeInTheDocument());
    expect(accountsApi.setAnchor).toHaveBeenCalledWith(fresh, { balance: "250.00", asOfDate: "2026-10-18" });
    await waitFor(() => expect(screen.getByTestId(`balance-sgd-${fresh}`)).toHaveTextContent("250.00"));
    expect(screen.getByTestId("combined-total")).toHaveTextContent("Combined total (3 accounts): SGD 2,130.00");
    expect(screen.getByTestId("account-status-message")).toHaveTextContent("Saved SGD 250.00 for 31 Aug 2026 on “Fresh”.");
    // everything that can show an account was read again
    await waitFor(() => expect(vi.mocked(balancesApi.getBalanceSeries).mock.calls.length).toBeGreaterThanOrEqual(2));
    expect(vi.mocked(balancesApi.getDiscrepancies).mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(vi.mocked(accountsApi.listAccounts).mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("opens the same dialog from the Accounts section, showing the balance it would replace", async () => {
    mockReads();
    setup();
    await userEvent.setup().click(await screen.findByTestId(`account-set-balance-${main}`));
    expect(screen.getByTestId("balance-dialog")).toHaveTextContent("Replace the balance of “Main”");
    expect(screen.getByTestId("balance-previous")).toHaveTextContent("Currently SGD 1,000.00 on 30 Jun 2026");
  });

  it("says so in the status line, and closes, when the account has gone", async () => {
    mockReads();
    vi.mocked(accountsApi.setAnchor).mockRejectedValue(new ApiError(404, { error: "account_not_found", message: "x" }));
    setup();
    const user = userEvent.setup();
    await user.click(await screen.findByTestId(`set-balance-${fresh}`));
    await user.type(screen.getByTestId("balance-input"), "5");
    await user.click(screen.getByTestId("balance-save"));
    await waitFor(() => expect(screen.queryByTestId("balance-dialog")).not.toBeInTheDocument());
    expect(screen.getByTestId("account-status-message")).toHaveTextContent("That account no longer exists; the list has been refreshed.");
  });
});

describe("BalancesTab: Save and next account", () => {
  const second: AccountDTO = { ...accountsListFixture().items.find((a) => a.id === fresh)!, id: "second-id", name: "Second" };

  it("opens the next account that needs a balance, with the date carried over and nothing typed", async () => {
    const accounts = [...accountsListFixture().items, second];
    mockReads(accounts);
    vi.mocked(accountsApi.setAnchor).mockImplementation(async () => anchorCreatedFixture());
    setup();
    const user = userEvent.setup();

    await user.click(await screen.findByTestId(`set-balance-${fresh}`));
    expect(screen.getByTestId("balance-save-next")).toBeInTheDocument();
    await user.type(screen.getByTestId("balance-input"), "100");
    fireEvent.change(screen.getByTestId("balance-date-input"), { target: { value: "2026-08-31" } });
    await user.click(screen.getByTestId("balance-save-next"));

    await waitFor(() => expect(screen.getByTestId("balance-dialog")).toHaveTextContent("Set the balance of “Second”"));
    expect(screen.getByTestId("balance-input")).toHaveValue("");
    expect(screen.getByTestId("balance-date-input")).toHaveValue("2026-08-31"); // the date of the balance just saved
    expect(screen.queryByTestId("balance-save-next")).not.toBeInTheDocument(); // nobody left after this one
    expect(accountsApi.setAnchor).toHaveBeenCalledWith(fresh, { balance: "100.00", asOfDate: "2026-08-31" });

    await user.type(screen.getByTestId("balance-input"), "50");
    await user.click(screen.getByTestId("balance-save"));
    await waitFor(() => expect(screen.queryByTestId("balance-dialog")).not.toBeInTheDocument());
    expect(accountsApi.setAnchor).toHaveBeenLastCalledWith("second-id", { balance: "50.00", asOfDate: "2026-08-31" });
  });

  it("is not offered when the account being saved is the only one that needs a balance", async () => {
    mockReads();
    setup();
    await userEvent.setup().click(await screen.findByTestId(`set-balance-${fresh}`));
    expect(screen.queryByTestId("balance-save-next")).not.toBeInTheDocument();
  });

  it("closes after a plain Save even when others still need a balance", async () => {
    mockReads([...accountsListFixture().items, second]);
    vi.mocked(accountsApi.setAnchor).mockImplementation(async () => anchorCreatedFixture());
    setup();
    const user = userEvent.setup();
    await user.click(await screen.findByTestId(`set-balance-${fresh}`));
    await user.type(screen.getByTestId("balance-input"), "100");
    await user.click(screen.getByTestId("balance-save"));
    await waitFor(() => expect(screen.queryByTestId("balance-dialog")).not.toBeInTheDocument());
  });
});
