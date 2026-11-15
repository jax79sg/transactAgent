import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as accountsApi from "../src/api/accounts";
import type { AccountDTO } from "../src/api/types";
import { PossibleDuplicatesNotice } from "../src/components/balances/PossibleDuplicatesNotice";
import { renderWithQueryClient } from "./balanceTestUtils";
import { accountsListFixture, anchorCreatedFixture, fixtureAccount } from "./balancesFixtures";

vi.mock("../src/api/accounts");

// The real case (issue #65): one DBS account listed twice because its statements spell the bank "DBS" and "DBS / POSB".
function twinAccounts(options: { bothHaveBalances: boolean }): AccountDTO[] {
  const anchor = anchorCreatedFixture().anchor;
  const base = { accountIdentifier: "1234567890123", currency: "SGD", type: "deposit" as const, canHaveAnchor: true };
  return [
    fixtureAccount("main", { ...base, id: "dbs-1", name: "DBS 6220", bankName: "DBS", statementCount: 1, anchor }),
    fixtureAccount("fresh", {
      ...base,
      id: "dbs-2",
      name: "DBS / POSB 6220",
      bankName: "DBS / POSB",
      statementCount: 4,
      anchor: options.bothHaveBalances ? anchor : null,
    }),
    ...accountsListFixture().items.filter((a) => a.type === "credit_card"),
  ];
}

function setup(accounts: AccountDTO[]) {
  vi.mocked(accountsApi.listAccounts).mockResolvedValue({ items: accounts });
  const onMessage = vi.fn();
  const view = renderWithQueryClient(<PossibleDuplicatesNotice onMessage={onMessage} />);
  return { ...view, onMessage };
}

describe("PossibleDuplicatesNotice", () => {
  it("says nothing when no two accounts share an account number", async () => {
    setup(accountsListFixture().items);
    await waitFor(() => expect(accountsApi.listAccounts).toHaveBeenCalled());
    expect(screen.queryByTestId("possible-duplicates")).not.toBeInTheDocument();
  });

  it("warns that the total counts the account twice when a balance is entered on both", async () => {
    setup(twinAccounts({ bothHaveBalances: true }));

    const notice = await screen.findByTestId("possible-duplicates");
    expect(notice).toHaveTextContent("“DBS / POSB 6220” and “DBS 6220” have the same account number");
    expect(notice).toHaveTextContent("A balance is entered on each, so the combined total counts this account twice");
  });

  it("is gentler when only one of them has a balance, since nothing is double-counted yet", async () => {
    setup(twinAccounts({ bothHaveBalances: false }));

    const notice = await screen.findByTestId("possible-duplicates");
    expect(notice).toHaveTextContent("may be one account listed twice");
    expect(notice).not.toHaveTextContent("counts this account twice");
  });

  it("opens the merge dialog on the account with fewer statements, leaving the choice of survivor to the owner", async () => {
    const user = userEvent.setup();
    setup(twinAccounts({ bothHaveBalances: true }));

    await user.click(await screen.findByTestId("merge-duplicates-dbs-2"));

    const dialog = await screen.findByTestId("merge-dialog");
    expect(dialog).toHaveTextContent("Merge “DBS 6220” into another account");
    expect(screen.getByTestId("merge-target-select")).toHaveValue("");
  });

  it("reports the outcome through the status line and goes away once merged", async () => {
    const user = userEvent.setup();
    const accounts = twinAccounts({ bothHaveBalances: false });
    const { onMessage } = setup(accounts);
    vi.mocked(accountsApi.mergeAccounts).mockImplementation(async () => {
      // after the merge the list has one account for that number
      vi.mocked(accountsApi.listAccounts).mockResolvedValue({ items: accounts.filter((a) => a.id !== "dbs-1") });
      return accounts[1];
    });

    await user.click(await screen.findByTestId("merge-duplicates-dbs-2"));
    await user.selectOptions(await screen.findByTestId("merge-target-select"), "dbs-2");
    await user.click(screen.getByTestId("merge-confirm"));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Merged “DBS 6220” into “DBS / POSB 6220”."));
    await waitFor(() => expect(screen.queryByTestId("possible-duplicates")).not.toBeInTheDocument());
  });
});
