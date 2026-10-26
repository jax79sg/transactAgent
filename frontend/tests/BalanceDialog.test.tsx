import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as accountsApi from "../src/api/accounts";
import { ApiError } from "../src/api/client";
import type { AccountDTO, AnchorResponse } from "../src/api/types";
import { BalanceDialog } from "../src/components/balances/BalanceDialog";
import { renderWithQueryClient } from "./balanceTestUtils";
import { anchorCreatedFixture, anchorReplacedFixture, fixtureAccount } from "./balancesFixtures";

vi.mock("../src/api/accounts");

const TODAY = "2026-10-18";

function setup(options: { account?: AccountDTO; canSaveAndNext?: boolean; defaultDate?: string } = {}) {
  const account = options.account ?? fixtureAccount("fresh");
  const onClose = vi.fn();
  const onSaved = vi.fn();
  const onGone = vi.fn();
  const view = renderWithQueryClient(
    <BalanceDialog
      account={account}
      defaultDate={options.defaultDate ?? TODAY}
      maxDate={TODAY}
      canSaveAndNext={options.canSaveAndNext ?? false}
      onClose={onClose}
      onSaved={onSaved}
      onGone={onGone}
    />,
  );
  const invalidate = vi.spyOn(view.queryClient, "invalidateQueries");
  return { ...view, account, onClose, onSaved, onGone, invalidate };
}

// Replaces whatever the field holds: a change starts with the current balance filled in (issue #57).
async function enter(balance: string) {
  const user = userEvent.setup();
  await user.clear(screen.getByTestId("balance-input"));
  await user.type(screen.getByTestId("balance-input"), balance);
  return user;
}

describe("BalanceDialog: what it says", () => {
  it("asks for a first balance in the account's currency, as the END-OF-DAY figure", () => {
    setup();
    const dialog = screen.getByTestId("balance-dialog");
    expect(dialog).toHaveTextContent("Set the balance of “Fresh”");
    expect(dialog).toHaveTextContent("In SGD.");
    expect(dialog).toHaveTextContent("end of that day, after that day's transactions");
    expect(screen.getByTestId("balance-save")).toHaveTextContent("Save balance");
    expect(screen.queryByTestId("balance-previous")).not.toBeInTheDocument();
  });

  it("names a foreign currency", () => {
    setup({ account: fixtureAccount("usd") });
    expect(screen.getByTestId("balance-dialog")).toHaveTextContent("In USD.");
    expect(screen.getByText(/Balance \(USD\)/)).toBeInTheDocument();
  });

  it("shows the value being replaced before the owner confirms", () => {
    setup({ account: fixtureAccount("main") });
    expect(screen.getByTestId("balance-dialog")).toHaveTextContent("Change the balance of “Main”");
    expect(screen.getByTestId("balance-previous")).toHaveTextContent("Currently SGD 1,000.00 on 30 Jun 2026. Saving replaces it.");
    expect(screen.getByTestId("balance-save")).toHaveTextContent("Save change");
  });

  it("starts a change with the current amount and its own date, not the date it was offered (issue #57)", () => {
    setup({ account: fixtureAccount("main"), defaultDate: "2026-10-18" });
    expect(screen.getByTestId("balance-input")).toHaveValue("1000.00");
    expect(screen.getByTestId("balance-date-input")).toHaveValue("2026-06-30");
  });

  it("selects the current amount, so typing overwrites it", () => {
    setup({ account: fixtureAccount("main") });
    const input = screen.getByTestId("balance-input") as HTMLInputElement;
    expect(input).toHaveFocus();
    expect([input.selectionStart, input.selectionEnd]).toEqual([0, input.value.length]);
  });

  it("starts a first balance empty, on the date it was offered", () => {
    setup({ defaultDate: "2026-09-30" });
    expect(screen.getByTestId("balance-input")).toHaveValue("");
    expect(screen.getByTestId("balance-date-input")).toHaveValue("2026-09-30");
  });

  it("starts on the date it was given and allows nothing after today or before 2000", () => {
    setup({ defaultDate: "2026-09-30" });
    const date = screen.getByTestId("balance-date-input");
    expect(date).toHaveValue("2026-09-30");
    expect(date).toHaveAttribute("max", TODAY);
    expect(date).toHaveAttribute("min", "2000-01-01");
  });
});

describe("BalanceDialog: saving", () => {
  it("fixes a mistyped amount without moving the balance to another date (issue #57)", async () => {
    const { account, onSaved } = setup({ account: fixtureAccount("main"), defaultDate: "2026-10-18" });
    const response = anchorReplacedFixture();
    vi.mocked(accountsApi.setAnchor).mockResolvedValue(response);
    const user = await enter("1,200.50");
    await user.click(screen.getByTestId("balance-save"));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith({ account, response, saveAndNext: false }));
    expect(accountsApi.setAnchor).toHaveBeenCalledWith(account.id, { balance: "1200.50", asOfDate: "2026-06-30" });
  });

  it("sends the canonical two-place balance and the date, then refreshes accounts and balances and reports", async () => {
    const { account, onSaved, invalidate } = setup();
    const response: AnchorResponse = anchorCreatedFixture();
    vi.mocked(accountsApi.setAnchor).mockResolvedValue(response);
    const user = await enter("1,500");

    await user.click(screen.getByTestId("balance-save"));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith({ account, response, saveAndNext: false }));
    expect(accountsApi.setAnchor).toHaveBeenCalledWith(account.id, { balance: "1500.00", asOfDate: TODAY });
    const keys = invalidate.mock.calls.map(([filters]) => (filters as { queryKey: unknown }).queryKey);
    expect(keys).toEqual(expect.arrayContaining([["accounts"], ["balances"]]));
  });

  it("sends a replacement the same way and passes the replaced value back", async () => {
    const { account, onSaved } = setup({ account: fixtureAccount("main") });
    const response = anchorReplacedFixture();
    vi.mocked(accountsApi.setAnchor).mockResolvedValue(response);
    const user = await enter("1200");
    fireEvent.change(screen.getByTestId("balance-date-input"), { target: { value: "2026-08-31" } });
    await user.click(screen.getByTestId("balance-save"));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith({ account, response, saveAndNext: false }));
    expect(accountsApi.setAnchor).toHaveBeenCalledWith(account.id, { balance: "1200.00", asOfDate: "2026-08-31" });
  });

  it("accepts a negative balance (an overdrawn account)", async () => {
    const { account } = setup();
    vi.mocked(accountsApi.setAnchor).mockResolvedValue(anchorCreatedFixture());
    const user = await enter("-42.5");
    await user.click(screen.getByTestId("balance-save"));
    await waitFor(() => expect(accountsApi.setAnchor).toHaveBeenCalledWith(account.id, { balance: "-42.50", asOfDate: TODAY }));
  });

  it("submits with Enter", async () => {
    setup();
    vi.mocked(accountsApi.setAnchor).mockResolvedValue(anchorCreatedFixture());
    const user = await enter("10");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(accountsApi.setAnchor).toHaveBeenCalledTimes(1));
  });

  it("offers Save and next account only when asked to, and reports that it was chosen", async () => {
    const { unmount } = setup({ canSaveAndNext: false });
    expect(screen.queryByTestId("balance-save-next")).not.toBeInTheDocument();
    unmount();

    const { account, onSaved } = setup({ canSaveAndNext: true });
    const response = anchorCreatedFixture();
    vi.mocked(accountsApi.setAnchor).mockResolvedValue(response);
    const user = await enter("10");
    await user.click(screen.getByTestId("balance-save-next"));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith({ account, response, saveAndNext: true }));
  });
});

describe("BalanceDialog: nothing is sent while what was typed is wrong", () => {
  it.each([
    ["", "Enter the balance."],
    ["abc", "That isn't a number. Use digits, for example 1,234.50."],
    ["1e5", "That isn't a number. Use digits, for example 1,234.50."],
    ["12.345", "Use at most two decimal places; the amount isn't rounded for you."],
  ])("a balance of %j is refused with its reason", async (typed, message) => {
    setup();
    const user = userEvent.setup();
    if (typed) await user.type(screen.getByTestId("balance-input"), typed);
    await user.click(screen.getByTestId("balance-save"));
    expect(await screen.findByTestId("balance-error")).toHaveTextContent(message);
    expect(accountsApi.setAnchor).not.toHaveBeenCalled();
  });

  it.each([
    ["", "Choose the date this balance applies to."],
    ["2026-10-19", "The date can't be after today."],
    ["1999-12-31", "Dates before 1 Jan 2000 aren't supported."],
  ])("a date of %j is refused", async (date, message) => {
    setup();
    const user = await enter("100");
    fireEvent.change(screen.getByTestId("balance-date-input"), { target: { value: date } });
    await user.click(screen.getByTestId("balance-save"));
    expect(await screen.findByTestId("balance-error")).toHaveTextContent(message);
    expect(accountsApi.setAnchor).not.toHaveBeenCalled();
  });

  it("takes the message away as soon as the owner changes the field", async () => {
    setup();
    const user = userEvent.setup();
    await user.click(screen.getByTestId("balance-save"));
    expect(await screen.findByTestId("balance-error")).toBeInTheDocument();
    await user.type(screen.getByTestId("balance-input"), "5");
    expect(screen.queryByTestId("balance-error")).not.toBeInTheDocument();
  });
});

describe("BalanceDialog: when the API refuses", () => {
  it.each([
    ["invalid_anchor_value", "Enter the balance as a number with at most two decimal places, for example 1,234.50."],
    ["anchor_date_in_future", "The date can't be after today."],
    ["anchor_date_out_of_range", "The date is too far back; dates before 1 Jan 2000 aren't supported."],
    ["not_a_deposit_account", "Only savings and current accounts have a balance. Change this account's type first."],
  ])("%s is worded and the dialog stays open", async (code, sentence) => {
    const { onSaved, invalidate } = setup();
    vi.mocked(accountsApi.setAnchor).mockRejectedValue(new ApiError(code === "not_a_deposit_account" ? 409 : 400, { error: code, message: "x" }));
    const user = await enter("100");
    await user.click(screen.getByTestId("balance-save"));
    expect(await screen.findByTestId("balance-error")).toHaveTextContent(sentence);
    expect(onSaved).not.toHaveBeenCalled();
    expect(invalidate).not.toHaveBeenCalled();
    expect(screen.getByTestId("balance-dialog")).toBeInTheDocument();
  });

  it("refreshes and reports when the account no longer exists, with no error box", async () => {
    const { onGone, onSaved } = setup();
    vi.mocked(accountsApi.setAnchor).mockRejectedValue(new ApiError(404, { error: "account_not_found", message: "x" }));
    const user = await enter("100");
    await user.click(screen.getByTestId("balance-save"));
    await waitFor(() => expect(onGone).toHaveBeenCalledWith("That account no longer exists; the list has been refreshed."));
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.queryByTestId("balance-error")).not.toBeInTheDocument();
  });

  it("switches both save buttons off while the request is in flight", async () => {
    const { account } = setup({ canSaveAndNext: true });
    let finish: (value: unknown) => void = () => {};
    vi.mocked(accountsApi.setAnchor).mockReturnValue(new Promise((resolve) => (finish = resolve)) as never);
    const user = await enter("100");
    await user.click(screen.getByTestId("balance-save"));
    await waitFor(() => expect(screen.getByTestId("balance-save")).toBeDisabled());
    expect(screen.getByTestId("balance-save-next")).toBeDisabled();
    await user.keyboard("{Enter}");
    expect(accountsApi.setAnchor).toHaveBeenCalledTimes(1);
    finish(anchorCreatedFixture());
    expect(account.id).toBeTruthy();
  });

  it("closes without sending anything on Cancel", async () => {
    const { onClose } = setup();
    const user = await enter("100");
    await user.click(screen.getByTestId("balance-cancel"));
    expect(onClose).toHaveBeenCalled();
    expect(accountsApi.setAnchor).not.toHaveBeenCalled();
  });
});
