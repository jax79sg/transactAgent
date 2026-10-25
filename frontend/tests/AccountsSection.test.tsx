import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as accountsApi from "../src/api/accounts";
import { ApiError } from "../src/api/client";
import { AccountsSection } from "../src/components/balances/AccountsSection";
import { WRITE_MUTATION_KEY } from "../src/components/balances/queries";
import { renderWithQueryClient } from "./balanceTestUtils";
import { accountsListFixture, FIXTURE_ACCOUNT_IDS, fixtureAccount } from "./balancesFixtures";

vi.mock("../src/api/accounts");

const listAccounts = () => vi.mocked(accountsApi.listAccounts);
const { main, fresh, card, usd, eur } = FIXTURE_ACCOUNT_IDS;

function setup(statusMessage: string | null = null) {
  const onSetBalance = vi.fn();
  const onMessage = vi.fn();
  const view = renderWithQueryClient(<AccountsSection statusMessage={statusMessage} onSetBalance={onSetBalance} onMessage={onMessage} />);
  return { ...view, onSetBalance, onMessage };
}

describe("AccountsSection: states", () => {
  it("says it is loading, then lists", async () => {
    listAccounts().mockResolvedValue(accountsListFixture());
    setup();
    expect(screen.getByTestId("accounts-loading")).toBeInTheDocument();
    expect(await screen.findByTestId(`account-row-${main}`)).toBeInTheDocument();
    expect(screen.queryByTestId("accounts-loading")).not.toBeInTheDocument();
  });

  it("explains when there are no accounts", async () => {
    listAccounts().mockResolvedValue({ items: [] });
    setup();
    expect(await screen.findByTestId("accounts-empty")).toHaveTextContent("No accounts yet. They are created when statements are ingested.");
  });

  it("shows the failure with Try again, and recovers", async () => {
    listAccounts().mockRejectedValueOnce(new ApiError(500, { error: "unknown", message: "x" }));
    setup();
    expect(await screen.findByTestId("accounts-error")).toHaveTextContent("The server had a problem. Please try again.");
    listAccounts().mockResolvedValue(accountsListFixture());
    await userEvent.setup().click(screen.getByTestId("accounts-retry"));
    expect(await screen.findByTestId(`account-row-${main}`)).toBeInTheDocument();
  });

  it("always has the status line ready for a screen reader, empty until something happens", async () => {
    listAccounts().mockResolvedValue(accountsListFixture());
    setup();
    const line = await screen.findByTestId("account-status-message");
    expect(line).toHaveAttribute("role", "status");
    expect(line).toHaveAttribute("aria-live", "polite");
    expect(line).toBeEmptyDOMElement();
  });

  it("shows the message it was given", async () => {
    listAccounts().mockResolvedValue(accountsListFixture());
    setup("Saved SGD 1,500.00 for 18 Oct 2026 on “Main”.");
    expect(await screen.findByTestId("account-status-message")).toHaveTextContent("Saved SGD 1,500.00 for 18 Oct 2026 on “Main”.");
  });
});

describe("AccountsSection: the list", () => {
  it("groups by type, in the order the API gives within each", async () => {
    listAccounts().mockResolvedValue(accountsListFixture());
    setup();
    await screen.findByTestId(`account-row-${main}`);
    const deposit = screen.getByTestId("accounts-group-deposit");
    expect(within(deposit).getAllByTestId(/^account-row-/).map((row) => row.getAttribute("data-testid"))).toEqual(
      [fresh, main, eur, usd].map((id) => `account-row-${id}`),
    );
    expect(within(screen.getByTestId("accounts-group-credit_card")).getByTestId(`account-row-${card}`)).toBeInTheDocument();
    expect(screen.queryByTestId("accounts-group-unknown")).not.toBeInTheDocument();
  });

  it("shows what an account is and has: identifier, bank, type, currency, balance entered, counts, last transaction", async () => {
    listAccounts().mockResolvedValue(accountsListFixture());
    setup();
    const row = await screen.findByTestId(`account-row-${main}`);
    expect(row).toHaveTextContent("Main");
    expect(row).toHaveTextContent("1234");
    expect(row).toHaveTextContent("DBS · Savings or current account · SGD");
    expect(row).toHaveTextContent("Balance entered: SGD 1,000.00 on 30 Jun 2026");
    expect(row).toHaveTextContent("2 statements · 4 transactions · 2 printed closing balances · last transaction 20 Jul 2026");
  });

  it("says when the owner chose the type, when there is no balance, and when there are no transactions", async () => {
    listAccounts().mockResolvedValue(accountsListFixture());
    setup();
    expect(await screen.findByTestId(`account-row-${card}`)).toHaveTextContent("Credit card (set by you)");
    expect(screen.getByTestId(`account-row-${card}`)).toHaveTextContent("Not in balances");
    expect(screen.getByTestId(`account-row-${fresh}`)).toHaveTextContent("No balance entered");
    expect(screen.getByTestId(`account-row-${fresh}`)).toHaveTextContent("no transactions");
  });

  it("tells same-named accounts apart by identifier and counts", async () => {
    const twin = (id: string, identifier: string, transactions: number) =>
      fixtureAccount("fresh", { id, name: "GXS Bank cket", accountIdentifier: identifier, transactionCount: transactions });
    listAccounts().mockResolvedValue({ items: [twin("t1", "c1", 31), twin("t2", "c2", 12)] });
    setup();
    expect(await screen.findByTestId("account-row-t1")).toHaveTextContent("GXS Bank cket");
    expect(screen.getByTestId("account-row-t1")).toHaveTextContent("c1");
    expect(screen.getByTestId("account-row-t1")).toHaveTextContent("31 transactions");
    expect(screen.getByTestId("account-row-t2")).toHaveTextContent("c2");
    expect(screen.getByTestId("account-row-t2")).toHaveTextContent("12 transactions");
  });
});

describe("AccountsSection: the actions", () => {
  it("offers a balance action only on a deposit account, worded for whether one exists", async () => {
    listAccounts().mockResolvedValue(accountsListFixture());
    setup();
    await screen.findByTestId(`account-row-${main}`);
    expect(screen.getByTestId(`account-set-balance-${main}`)).toHaveTextContent("Change balance");
    expect(screen.getByTestId(`account-set-balance-${fresh}`)).toHaveTextContent("Set balance");
    expect(screen.queryByTestId(`account-set-balance-${card}`)).not.toBeInTheDocument();
    for (const id of [main, fresh, card]) {
      expect(screen.getByTestId(`account-rename-${id}`)).toBeInTheDocument();
      expect(screen.getByTestId(`account-change-type-${id}`)).toBeInTheDocument();
      expect(screen.getByTestId(`account-merge-${id}`)).toBeInTheDocument();
    }
  });

  it("asks the tab to open the balance dialog for the account", async () => {
    listAccounts().mockResolvedValue(accountsListFixture());
    const { onSetBalance } = setup();
    await userEvent.setup().click(await screen.findByTestId(`account-set-balance-${fresh}`));
    expect(onSetBalance).toHaveBeenCalledWith(fresh);
  });

  it("opens the rename, type and merge dialogs for the right account, and closes them on Cancel", async () => {
    listAccounts().mockResolvedValue(accountsListFixture());
    setup();
    const user = userEvent.setup();

    await user.click(await screen.findByTestId(`account-rename-${main}`));
    expect(screen.getByTestId("rename-dialog")).toHaveTextContent("Rename “Main”");
    await user.click(screen.getByTestId("rename-cancel"));
    expect(screen.queryByTestId("rename-dialog")).not.toBeInTheDocument();

    await user.click(screen.getByTestId(`account-change-type-${card}`));
    expect(screen.getByTestId("type-dialog")).toHaveTextContent("Change the type of “Visa Card”");
    await user.click(screen.getByTestId("type-cancel"));
    expect(screen.queryByTestId("type-dialog")).not.toBeInTheDocument();

    await user.click(screen.getByTestId(`account-merge-${fresh}`));
    expect(screen.getByTestId("merge-dialog")).toHaveTextContent("Merge “Fresh” into another account");
    await user.click(screen.getByTestId("merge-cancel"));
    expect(screen.queryByTestId("merge-dialog")).not.toBeInTheDocument();
  });

  it("after a rename: closes the dialog, reports it, and shows the new name from a refreshed list", async () => {
    const renamed = accountsListFixture();
    renamed.items = renamed.items.map((a) => (a.id === main ? { ...a, name: "Everyday" } : a));
    listAccounts().mockResolvedValueOnce(accountsListFixture()).mockResolvedValue(renamed);
    vi.mocked(accountsApi.updateAccount).mockResolvedValue(renamed.items.find((a) => a.id === main)!);
    const { onMessage } = setup();
    const user = userEvent.setup();

    await user.click(await screen.findByTestId(`account-rename-${main}`));
    await user.clear(screen.getByTestId("rename-input"));
    await user.type(screen.getByTestId("rename-input"), "Everyday");
    await user.click(screen.getByTestId("rename-save"));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Renamed “Main” to “Everyday”."));
    expect(screen.queryByTestId("rename-dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId(`account-row-${main}`)).toHaveTextContent("Everyday"));
  });

  it("after a merge: the absorbed account is gone from the refreshed list", async () => {
    const after = accountsListFixture();
    after.items = after.items.filter((a) => a.id !== fresh);
    listAccounts().mockResolvedValueOnce(accountsListFixture()).mockResolvedValue(after);
    vi.mocked(accountsApi.mergeAccounts).mockResolvedValue(after.items.find((a) => a.id === main)!);
    const { onMessage } = setup();
    const user = userEvent.setup();

    await user.click(await screen.findByTestId(`account-merge-${fresh}`));
    await user.selectOptions(screen.getByTestId("merge-target-select"), main);
    await user.click(screen.getByTestId("merge-confirm"));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Merged “Fresh” into “Main”."));
    await waitFor(() => expect(screen.queryByTestId(`account-row-${fresh}`)).not.toBeInTheDocument());
  });

  it("switches every action off while a write is in flight", async () => {
    listAccounts().mockResolvedValue(accountsListFixture());
    const { queryClient } = setup();
    await screen.findByTestId(`account-row-${usd}`);
    expect(screen.getByTestId(`account-rename-${usd}`)).toBeEnabled();
    await act(async () => {
      void queryClient
        .getMutationCache()
        .build(queryClient, { mutationKey: WRITE_MUTATION_KEY, mutationFn: () => new Promise<never>(() => {}) })
        .execute(undefined);
    });
    await waitFor(() => expect(screen.getByTestId(`account-rename-${usd}`)).toBeDisabled());
    for (const testId of [`account-set-balance-${usd}`, `account-change-type-${usd}`, `account-merge-${usd}`]) {
      expect(screen.getByTestId(testId)).toBeDisabled();
    }
  });
});
