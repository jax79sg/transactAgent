import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as accountsApi from "../src/api/accounts";
import { ApiError } from "../src/api/client";
import type { AccountDTO } from "../src/api/types";
import { MergeDialog } from "../src/components/balances/MergeDialog";
import { renderWithQueryClient } from "./balanceTestUtils";
import { accountsListFixture, fixtureAccount, mergeSuccessFixture } from "./balancesFixtures";

vi.mock("../src/api/accounts");

const ANCHOR_B = { balance: "480.00", asOfDate: "2026-06-01", updatedAt: "2026-06-02T00:00:00Z" };

function setup(absorbed: AccountDTO, accounts: AccountDTO[] = accountsListFixture().items) {
  const onClose = vi.fn();
  const onDone = vi.fn();
  const view = renderWithQueryClient(<MergeDialog absorbed={absorbed} accounts={accounts} onClose={onClose} onDone={onDone} />);
  const invalidate = vi.spyOn(view.queryClient, "invalidateQueries");
  return { ...view, onClose, onDone, invalidate };
}

async function choose(account: AccountDTO) {
  const user = userEvent.setup();
  await user.selectOptions(screen.getByTestId("merge-target-select"), account.id);
  return user;
}

describe("MergeDialog: who can be kept", () => {
  it("offers only accounts in the same currency, never the account itself, and confirms nothing yet", () => {
    setup(fixtureAccount("fresh")); // SGD
    const options = within(screen.getByTestId("merge-target-select")).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([
      "Choose the account to keep",
      "Main · DBS 1234 · 2 statements",
      "Visa Card · DBS 9999 · 1 statement",
    ]);
    expect(screen.getByTestId("merge-confirm")).toBeDisabled();
    expect(screen.queryByTestId("merge-preview")).not.toBeInTheDocument();
  });

  it("says so when there is no other account in that currency", () => {
    setup(fixtureAccount("usd")); // the only USD account
    expect(screen.getByTestId("merge-no-candidates")).toHaveTextContent("There is no other USD account to merge into.");
    expect(screen.queryByTestId("merge-target-select")).not.toBeInTheDocument();
    expect(screen.getByTestId("merge-confirm")).toBeDisabled();
  });
});

describe("MergeDialog: the preview", () => {
  it("states what moves, what stays, what happens to later statements, and that it cannot be undone", async () => {
    const absorbed = fixtureAccount("main"); // 2 statements, 4 transactions
    setup(absorbed, [absorbed, fixtureAccount("fresh")]);
    await choose(fixtureAccount("fresh"));
    const preview = screen.getByTestId("merge-preview");
    expect(preview).toHaveTextContent("All 2 statements and 4 transactions of “Main” will count under “Fresh”.");
    expect(preview).toHaveTextContent("“Main” disappears from the list; “Fresh” keeps its name.");
    expect(preview).toHaveTextContent("Later statements that match “Main” will be filed under “Fresh”.");
    expect(preview).toHaveTextContent("This can't be undone.");
  });

  it("uses the singular for one statement and one transaction", async () => {
    const absorbed = fixtureAccount("fresh", { statementCount: 1, transactionCount: 1 });
    setup(absorbed, [absorbed, fixtureAccount("main")]);
    await choose(fixtureAccount("main"));
    expect(screen.getByTestId("merge-preview")).toHaveTextContent("All 1 statement and 1 transaction of");
  });

  it("says the kept account takes the type the owner set on the other one, only when that is what happens", async () => {
    const absorbed = fixtureAccount("card"); // a credit card the owner chose
    setup(absorbed, [absorbed, fixtureAccount("fresh")]); // Fresh: deposit, not chosen by the owner
    await choose(fixtureAccount("fresh"));
    expect(screen.getByTestId("merge-type-change")).toHaveTextContent(
      "“Fresh” becomes a credit card because you set that type on “Visa Card”.",
    );
  });

  it("says nothing about the type when it does not change", async () => {
    const absorbed = fixtureAccount("fresh");
    setup(absorbed, [absorbed, fixtureAccount("main")]);
    await choose(fixtureAccount("main"));
    expect(screen.queryByTestId("merge-type-change")).not.toBeInTheDocument();
  });

  it("names the one entered balance that will be kept, when only one account has one", async () => {
    const absorbed = fixtureAccount("fresh"); // none
    setup(absorbed, [absorbed, fixtureAccount("main")]); // Main: 1,000.00 on 30 Jun 2026
    await choose(fixtureAccount("main"));
    expect(screen.getByTestId("merge-anchor-kept")).toHaveTextContent(
      "The balance entered for “Main” (SGD 1,000.00 on 30 Jun 2026) will be kept.",
    );
    expect(screen.queryByTestId("merge-keep-choice")).not.toBeInTheDocument();
    expect(screen.getByTestId("merge-confirm")).toBeEnabled();
  });

  it("says nothing about balances when neither has one", async () => {
    const absorbed = fixtureAccount("fresh");
    const other = fixtureAccount("card", { type: "deposit", typeSetByUser: false, canHaveAnchor: true });
    setup(absorbed, [absorbed, other]);
    await choose(other);
    expect(screen.queryByTestId("merge-anchor-kept")).not.toBeInTheDocument();
    expect(screen.queryByTestId("merge-keep-choice")).not.toBeInTheDocument();
  });
});

describe("MergeDialog: both accounts have a balance entered", () => {
  const absorbed = fixtureAccount("fresh", { anchor: ANCHOR_B });
  const survivor = fixtureAccount("main");

  it("makes the owner choose which to keep, with nothing preselected, and Merge off until they do", async () => {
    setup(absorbed, [absorbed, survivor]);
    await choose(survivor);
    const radios = within(screen.getByTestId("merge-keep-choice")).getAllByRole("radio");
    expect(radios).toHaveLength(2);
    radios.forEach((radio) => expect(radio).not.toBeChecked());
    expect(screen.getByTestId(`merge-keep-${survivor.id}`)).toBeInTheDocument();
    expect(screen.getByTestId(`merge-keep-${absorbed.id}`)).toBeInTheDocument();
    expect(screen.getByTestId("merge-keep-choice")).toHaveTextContent("“Main”: SGD 1,000.00 on 30 Jun 2026");
    expect(screen.getByTestId("merge-keep-choice")).toHaveTextContent("“Fresh”: SGD 480.00 on 1 Jun 2026");
    expect(screen.getByTestId("merge-confirm")).toBeDisabled();
  });

  it("sends keepAnchorFrom with the chosen account", async () => {
    setup(absorbed, [absorbed, survivor]);
    vi.mocked(accountsApi.mergeAccounts).mockResolvedValue(mergeSuccessFixture());
    const user = await choose(survivor);
    await user.click(screen.getByTestId(`merge-keep-${absorbed.id}`));
    await user.click(screen.getByTestId("merge-confirm"));
    await waitFor(() =>
      expect(accountsApi.mergeAccounts).toHaveBeenCalledWith(survivor.id, { absorbedAccountId: absorbed.id, keepAnchorFrom: absorbed.id }),
    );
  });

  it("forgets the choice when a different account is picked", async () => {
    const third = fixtureAccount("card", { type: "deposit", canHaveAnchor: true, anchor: ANCHOR_B });
    setup(absorbed, [absorbed, survivor, third]);
    const user = await choose(survivor);
    await user.click(screen.getByTestId(`merge-keep-${survivor.id}`));
    expect(screen.getByTestId("merge-confirm")).toBeEnabled();
    await user.selectOptions(screen.getByTestId("merge-target-select"), third.id);
    expect(screen.getByTestId("merge-confirm")).toBeDisabled();
  });
});

describe("MergeDialog: merging", () => {
  it("sends the request to the KEPT account's path, naming the absorbed one, with no balance choice when none is needed", async () => {
    const absorbed = fixtureAccount("fresh");
    const survivor = fixtureAccount("main");
    const { onDone, invalidate } = setup(absorbed, [absorbed, survivor]);
    vi.mocked(accountsApi.mergeAccounts).mockResolvedValue(mergeSuccessFixture());
    const user = await choose(survivor);

    await user.click(screen.getByTestId("merge-confirm"));

    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Merged “Fresh” into “Main”."));
    expect(accountsApi.mergeAccounts).toHaveBeenCalledWith(survivor.id, { absorbedAccountId: absorbed.id });
    const keys = invalidate.mock.calls.map(([filters]) => (filters as { queryKey: unknown }).queryKey);
    expect(keys).toEqual(expect.arrayContaining([["accounts"], ["balances"]]));
  });

  it("switches Merge off while the request is in flight", async () => {
    const absorbed = fixtureAccount("fresh");
    const survivor = fixtureAccount("main");
    setup(absorbed, [absorbed, survivor]);
    let finish: (value: unknown) => void = () => {};
    vi.mocked(accountsApi.mergeAccounts).mockReturnValue(new Promise((resolve) => (finish = resolve)) as never);
    const user = await choose(survivor);
    await user.click(screen.getByTestId("merge-confirm"));
    await waitFor(() => expect(screen.getByTestId("merge-confirm")).toBeDisabled());
    expect(accountsApi.mergeAccounts).toHaveBeenCalledTimes(1);
    finish(mergeSuccessFixture());
  });

  it.each([
    ["merge_appear_together", 409, /listed together on one statement.*rename them instead/],
    ["merge_currency_mismatch", 409, /different currencies/],
    ["merge_anchor_choice_required", 409, /Choose which one to keep/],
    ["merge_anchor_choice_invalid", 400, /Choose the balance of one of these two accounts/],
    ["merge_same_account", 400, /Choose a different account/],
  ])("shows the refusal %s in the dialog, which stays open, nothing reported", async (code, status, pattern) => {
    const absorbed = fixtureAccount("fresh");
    const survivor = fixtureAccount("main");
    const { onDone, invalidate } = setup(absorbed, [absorbed, survivor]);
    vi.mocked(accountsApi.mergeAccounts).mockRejectedValue(new ApiError(status, { error: code, message: "x" }));
    const user = await choose(survivor);
    await user.click(screen.getByTestId("merge-confirm"));

    expect(await screen.findByTestId("merge-error")).toHaveTextContent(pattern);
    expect(onDone).not.toHaveBeenCalled();
    expect(invalidate).not.toHaveBeenCalled();
    expect(screen.getByTestId("merge-dialog")).toBeInTheDocument();
  });

  it("refreshes and reports when one of the accounts no longer exists", async () => {
    const absorbed = fixtureAccount("fresh");
    const survivor = fixtureAccount("main");
    const { onDone } = setup(absorbed, [absorbed, survivor]);
    vi.mocked(accountsApi.mergeAccounts).mockRejectedValue(new ApiError(404, { error: "account_not_found", message: "x" }));
    const user = await choose(survivor);
    await user.click(screen.getByTestId("merge-confirm"));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("That account no longer exists; the list has been refreshed."));
    expect(screen.queryByTestId("merge-error")).not.toBeInTheDocument();
  });

  it("closes without sending anything on Cancel", async () => {
    const absorbed = fixtureAccount("fresh");
    const { onClose } = setup(absorbed, [absorbed, fixtureAccount("main")]);
    await userEvent.setup().click(screen.getByTestId("merge-cancel"));
    expect(onClose).toHaveBeenCalled();
    expect(accountsApi.mergeAccounts).not.toHaveBeenCalled();
  });
});
