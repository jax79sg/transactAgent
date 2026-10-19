import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import * as balancesApi from "../src/api/balances";
import { ApiError } from "../src/api/client";
import type { DiscrepanciesResponse } from "../src/api/types";
import { DiscrepancyPanel } from "../src/components/balances/DiscrepancyPanel";
import { renderWithQueryClient } from "./balanceTestUtils";
import { discrepanciesFixture, FIXTURE_ACCOUNT_IDS } from "./balancesFixtures";

vi.mock("../src/api/balances");

const getDiscrepancies = () => vi.mocked(balancesApi.getDiscrepancies);
const MAIN = FIXTURE_ACCOUNT_IDS.main;

function setup() {
  return renderWithQueryClient(
    <MemoryRouter>
      <DiscrepancyPanel />
    </MemoryRouter>,
  );
}

async function opened() {
  setup();
  const user = userEvent.setup();
  await user.click(await screen.findByTestId("discrepancy-toggle"));
  return user;
}

describe("DiscrepancyPanel: the summary line", () => {
  it("counts the accounts with differences and keeps the details closed", async () => {
    getDiscrepancies().mockResolvedValue(discrepanciesFixture());
    setup();
    expect(await screen.findByTestId("discrepancy-summary")).toHaveTextContent("1 account has differences with its statements.");
    expect(screen.getByTestId("discrepancy-toggle")).toHaveTextContent("Show details");
    expect(screen.getByTestId("discrepancy-toggle")).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("discrepancy-details")).not.toBeInTheDocument();
  });

  it("says the statements agree when accounts were checked and nothing differs", async () => {
    getDiscrepancies().mockResolvedValue({ tolerance: "0.00", accountsChecked: 3, items: [] });
    setup();
    expect(await screen.findByTestId("discrepancy-summary")).toHaveTextContent("Your statements agree with your balances (3 accounts checked).");
    expect(screen.queryByTestId("discrepancy-toggle")).not.toBeInTheDocument();
  });

  it("uses the singular when one account was checked", async () => {
    getDiscrepancies().mockResolvedValue({ tolerance: "0.00", accountsChecked: 1, items: [] });
    setup();
    expect(await screen.findByTestId("discrepancy-summary")).toHaveTextContent("(1 account checked)");
  });

  it("shows nothing at all when no account has an entered balance, so nothing was checked", async () => {
    getDiscrepancies().mockResolvedValue({ tolerance: "0.00", accountsChecked: 0, items: [] });
    const { container } = setup();
    await vi.waitFor(() => expect(getDiscrepancies()).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("says it could not check, with a way to try again, and does not throw the rest of the tab off", async () => {
    getDiscrepancies().mockRejectedValueOnce(new ApiError(500, { error: "unknown", message: "x" }));
    setup();
    expect(await screen.findByTestId("discrepancy-error")).toHaveTextContent("Couldn't check statement differences.");
    expect(getDiscrepancies()).toHaveBeenCalledTimes(1);

    getDiscrepancies().mockResolvedValue(discrepanciesFixture());
    await userEvent.setup().click(screen.getByTestId("discrepancy-retry"));
    expect(await screen.findByTestId("discrepancy-summary")).toBeInTheDocument();
  });
});

describe("DiscrepancyPanel: the details", () => {
  it("opens and closes on the button", async () => {
    getDiscrepancies().mockResolvedValue(discrepanciesFixture());
    const user = await opened();
    expect(screen.getByTestId("discrepancy-details")).toBeInTheDocument();
    expect(screen.getByTestId("discrepancy-toggle")).toHaveTextContent("Hide details");
    expect(screen.getByTestId("discrepancy-toggle")).toHaveAttribute("aria-expanded", "true");
    await user.click(screen.getByTestId("discrepancy-toggle"));
    expect(screen.queryByTestId("discrepancy-details")).not.toBeInTheDocument();
  });

  it("names the account and how much was checked", async () => {
    getDiscrepancies().mockResolvedValue(discrepanciesFixture());
    await opened();
    expect(screen.getByTestId(`discrepancy-account-${MAIN}`)).toHaveTextContent(
      "Main (SGD): 2 statements and 1 statement-to-statement interval checked",
    );
  });

  it("shows the statement that differs, what it says against what the balance works out to, and the difference in words", async () => {
    getDiscrepancies().mockResolvedValue(discrepanciesFixture());
    await opened();
    const statementId = discrepanciesFixture().items[0].statementDifferences[0].statementId;
    const row = screen.getByTestId(`statement-difference-row-${statementId}`);
    expect(row).toHaveTextContent("Statement closing 31 Jul 2026");
    expect(row).toHaveTextContent("1,100.00");
    expect(row).toHaveTextContent("1,030.00");
    expect(row).toHaveTextContent("+SGD 70.00 (statement shows more)");
  });

  it("shows the interval where transactions do not explain the change", async () => {
    getDiscrepancies().mockResolvedValue(discrepanciesFixture());
    await opened();
    const gap = discrepanciesFixture().items[0].periodGaps[0];
    const row = screen.getByTestId(`period-gap-row-${gap.fromStatementId}-${gap.toStatementId}`);
    expect(row).toHaveTextContent("30 Jun 2026 to 31 Jul 2026");
    expect(row).toHaveTextContent("100.00");
    expect(row).toHaveTextContent("30.00");
    expect(row).toHaveTextContent("+SGD 70.00 (statement shows more)");
  });

  it("explains both views, and which one goes away when the entered balance is corrected", async () => {
    getDiscrepancies().mockResolvedValue(discrepanciesFixture());
    await opened();
    const details = screen.getByTestId("discrepancy-details");
    expect(details).toHaveTextContent("Correct your entered balance and these disappear.");
    expect(details).toHaveTextContent("This does not depend on your entered balance and stays until the transactions are fixed.");
  });

  it("states the tolerance with a link to Settings, and that only accounts with an entered balance are checked", async () => {
    getDiscrepancies().mockResolvedValue({ ...discrepanciesFixture(), tolerance: "0.50" });
    await opened();
    const footer = screen.getByTestId("discrepancy-footer");
    expect(footer).toHaveTextContent("Differences larger than 0.50 are listed");
    expect(within(footer).getByRole("link", { name: "Settings under Balances" })).toHaveAttribute("href", "/settings");
    expect(footer).toHaveTextContent("Only accounts with an entered balance are checked.");
  });

  it("words a negative difference as the statement showing less", async () => {
    const data = discrepanciesFixture();
    data.items[0].statementDifferences[0].difference = "-12.34";
    getDiscrepancies().mockResolvedValue(data);
    await opened();
    expect(screen.getByTestId("discrepancy-details")).toHaveTextContent("SGD -12.34 (statement shows less)");
  });

  it("shows only the table that has rows", async () => {
    const data = discrepanciesFixture();
    data.items[0].statementDifferences = [];
    getDiscrepancies().mockResolvedValue(data);
    await opened();
    expect(screen.queryByText("Statements that differ from your entered balance")).not.toBeInTheDocument();
    expect(screen.getByText("Intervals where transactions don't explain the change")).toBeInTheDocument();
  });

  it("copes with statement ids that are null, giving each row its own key and test id", async () => {
    const data = discrepanciesFixture();
    const gap = data.items[0].periodGaps[0];
    data.items[0].statementDifferences[0].statementId = null;
    data.items[0].periodGaps = [
      { ...gap, fromStatementId: null, toStatementId: null, fromDate: "2026-05-31", toDate: "2026-06-30" },
      { ...gap, fromStatementId: null, toStatementId: null, fromDate: "2026-06-30", toDate: "2026-07-31" },
    ];
    getDiscrepancies().mockResolvedValue(data);
    await opened();
    expect(screen.getByTestId("statement-difference-row-2026-07-31")).toBeInTheDocument();
    expect(screen.getByTestId("period-gap-row-2026-05-31-2026-06-30")).toBeInTheDocument();
    expect(screen.getByTestId("period-gap-row-2026-06-30-2026-07-31")).toBeInTheDocument();
  });

  it("lists accounts by name and each interval by date", async () => {
    const data: DiscrepanciesResponse = discrepanciesFixture();
    const main = data.items[0];
    data.items = [
      { ...main, accountId: "z", name: "zeta" },
      { ...main, accountId: "a", name: "Alpha" },
    ];
    getDiscrepancies().mockResolvedValue(data);
    await opened();
    const blocks = screen.getAllByTestId(/^discrepancy-account-/).map((el) => el.getAttribute("data-testid"));
    expect(blocks).toEqual(["discrepancy-account-a", "discrepancy-account-z"]);
  });
});
