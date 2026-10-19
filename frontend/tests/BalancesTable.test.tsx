import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { AccountBalanceDTO, BalancesResponse } from "../src/api/types";
import { BalancesTable } from "../src/components/balances/BalancesTable";
import { WRITE_MUTATION_KEY } from "../src/components/balances/queries";
import { renderWithQueryClient } from "./balanceTestUtils";
import { balancesDateFixture, FIXTURE_ACCOUNT_IDS } from "./balancesFixtures";

const { main, usd, eur, fresh } = FIXTURE_ACCOUNT_IDS;

function show(response: BalancesResponse = balancesDateFixture(), onSetBalance = vi.fn()) {
  const view = renderWithQueryClient(<BalancesTable response={response} onSetBalance={onSetBalance} />);
  return { ...view, onSetBalance };
}

function rowOrder() {
  return within(screen.getByTestId("balances-table"))
    .getAllByTestId(/^balance-row-/)
    .map((row) => row.getAttribute("data-testid"));
}

describe("BalancesTable: rows", () => {
  it("lists one row per account in the order the API gives", () => {
    show();
    expect(rowOrder()).toEqual([`balance-row-${fresh}`, `balance-row-${main}`, `balance-row-${eur}`, `balance-row-${usd}`]);
    expect(screen.getByTestId(`balance-row-${main}`)).toHaveTextContent("Main");
    expect(screen.getByTestId(`balance-row-${main}`)).toHaveTextContent("DBS");
  });

  it("shows a balance in SGD with what it was worked from and the account's last transaction", () => {
    show();
    expect(screen.getByTestId(`balance-sgd-${main}`)).toHaveTextContent("1,100.00");
    expect(screen.getByTestId(`balance-basis-${main}`)).toHaveTextContent("From the statement closing balance of 31 Jul 2026");
    expect(screen.getByTestId(`balance-row-${main}`)).toHaveTextContent("20 Jul 2026");
    expect(screen.queryByTestId(`balance-approx-${main}`)).not.toBeInTheDocument();
  });

  it("marks a converted figure approximate, in words, and shows the native amount with its currency", () => {
    show();
    expect(screen.getByTestId(`balance-sgd-${usd}`)).toHaveTextContent("≈ 780.00");
    expect(screen.getByTestId(`balance-approx-${usd}`)).toHaveTextContent("approximate: exchange rate of 20 Jul 2026");
    expect(screen.getByTestId(`balance-native-${usd}`)).toHaveTextContent("600.00 USD");
    expect(screen.getByTestId(`balance-basis-${usd}`)).toHaveTextContent("From your entered balance of 1 Jul 2026");
  });

  it("shows 'Anchor required' with a Set balance button that names its account, and no figures", async () => {
    const { onSetBalance } = show();
    const row = screen.getByTestId(`balance-row-${fresh}`);
    expect(within(row).getByTestId(`balance-status-${fresh}`)).toHaveTextContent("Anchor required");
    expect(screen.queryByTestId(`balance-sgd-${fresh}`)).not.toBeInTheDocument();
    await userEvent.setup().click(within(row).getByTestId(`set-balance-${fresh}`));
    expect(onSetBalance).toHaveBeenCalledWith(fresh);
  });

  it("shows an unavailable conversion in words, still giving the account's own-currency figure", () => {
    show();
    expect(screen.getByTestId(`balance-status-${eur}`)).toHaveTextContent("Unavailable: no exchange rate");
    expect(screen.getByTestId(`balance-native-${eur}`)).toHaveTextContent("200.00 EUR");
    expect(screen.queryByTestId(`balance-sgd-${eur}`)).not.toBeInTheDocument();
    expect(screen.queryByTestId(`set-balance-${eur}`)).not.toBeInTheDocument(); // it HAS a balance: the problem is the rate
  });

  it("shows a negative balance with its minus sign and a red tone", () => {
    const response = balancesDateFixture();
    response.accounts.find((a) => a.accountId === main)!.balanceSgd = "-50.00";
    show(response);
    const cell = screen.getByTestId(`balance-sgd-${main}`);
    expect(cell).toHaveTextContent("-50.00");
    expect(cell.className).toContain("red");
  });

  it("never shows a negative zero", () => {
    const response = balancesDateFixture();
    response.accounts.find((a) => a.accountId === main)!.balanceSgd = "-0.00";
    show(response);
    expect(screen.getByTestId(`balance-sgd-${main}`)).toHaveTextContent(/^0\.00$/);
  });

  it("has a column for own-currency figures only when some account is not in SGD", () => {
    const { unmount } = show();
    expect(screen.getByRole("columnheader", { name: "Balance" })).toBeInTheDocument();
    unmount();

    const response = balancesDateFixture();
    response.accounts = response.accounts.filter((a) => a.currency === "SGD");
    show(response);
    expect(screen.queryByRole("columnheader", { name: "Balance" })).not.toBeInTheDocument();
    expect(screen.queryByTestId(`balance-native-${main}`)).not.toBeInTheDocument();
  });
});

describe("BalancesTable: the total", () => {
  it("states the total, how many accounts are in it, and every account that is not", () => {
    show();
    expect(screen.getByTestId("combined-total")).toHaveTextContent("Combined total (2 accounts): SGD 1,880.00");
    expect(screen.getByTestId("combined-exclusions")).toHaveTextContent(
      "Not included: Fresh (anchor required), Offshore EUR (no exchange rate)",
    );
    expect(screen.getByTestId("balances-approx-note")).toBeInTheDocument();
    expect(screen.queryByTestId("balances-explainer")).not.toBeInTheDocument();
  });

  it("says 1 account in the singular and leaves out the approximate note when nothing is approximate", () => {
    const response = balancesDateFixture();
    response.accounts = response.accounts.filter((a) => a.accountId !== usd);
    response.combinedIncludesCount = 1;
    response.combinedTotalSgd = "1100.00";
    response.hasApproximate = false;
    show(response);
    expect(screen.getByTestId("combined-total")).toHaveTextContent("Combined total (1 account): SGD 1,100.00");
    expect(screen.queryByTestId("balances-approx-note")).not.toBeInTheDocument();
  });

  it("says no account has a balance when none does, and explains what an anchor is", () => {
    const response = balancesDateFixture();
    response.accounts = response.accounts.filter((a) => a.status === "anchor_required");
    response.combinedTotalSgd = null;
    response.combinedIncludesCount = 0;
    response.hasApproximate = false;
    response.excluded = response.excluded.filter((e) => e.reason === "anchor_required");
    show(response);
    expect(screen.getByTestId("combined-total")).toHaveTextContent("No account has a balance yet. Enter one for each account to see a total.");
    expect(screen.getByTestId("balances-explainer")).toHaveTextContent("An anchor is a balance you know to be real on a date");
  });

  it("states no exclusion when nothing is excluded", () => {
    const response = balancesDateFixture();
    response.excluded = [];
    show(response);
    expect(screen.queryByTestId("combined-exclusions")).not.toBeInTheDocument();
  });

  it("explains the empty case instead of showing a blank panel", () => {
    const response = balancesDateFixture();
    response.accounts = [];
    response.excluded = [];
    response.combinedTotalSgd = null;
    response.combinedIncludesCount = 0;
    show(response);
    expect(screen.getByTestId("balances-empty-state")).toHaveTextContent("No savings or current accounts yet.");
    expect(screen.queryByTestId("balances-table")).not.toBeInTheDocument();
  });

  it("switches the Set balance buttons off while an account write is in flight", async () => {
    const { queryClient } = show();
    expect(screen.getByTestId(`set-balance-${fresh}`)).toBeEnabled();
    await act(async () => {
      void queryClient
        .getMutationCache()
        .build(queryClient, { mutationKey: WRITE_MUTATION_KEY, mutationFn: () => new Promise<never>(() => {}) })
        .execute(undefined);
    });
    // React Query tells its subscribers on the next tick, so the button follows a moment later.
    await waitFor(() => expect(screen.getByTestId(`set-balance-${fresh}`)).toBeDisabled());
  });
});

describe("BalancesTable: types", () => {
  it("accepts the API's own account shape for every status", () => {
    const statuses = balancesDateFixture().accounts.map((a: AccountBalanceDTO) => a.status);
    expect(new Set(statuses)).toEqual(new Set(["ok", "anchor_required", "fx_unavailable"]));
  });
});
