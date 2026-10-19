import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as accountsApi from "../src/api/accounts";
import { ApiError } from "../src/api/client";
import { ChangeTypeDialog } from "../src/components/balances/ChangeTypeDialog";
import { renderWithQueryClient } from "./balanceTestUtils";
import { fixtureAccount } from "./balancesFixtures";

vi.mock("../src/api/accounts");

function setup(account = fixtureAccount("main")) {
  const onClose = vi.fn();
  const onDone = vi.fn();
  const view = renderWithQueryClient(<ChangeTypeDialog account={account} onClose={onClose} onDone={onDone} />);
  const invalidate = vi.spyOn(view.queryClient, "invalidateQueries");
  return { ...view, account, onClose, onDone, invalidate };
}

describe("ChangeTypeDialog", () => {
  it("opens on the current type with Save off and no notes", () => {
    setup();
    expect(screen.getByTestId("type-option-deposit")).toBeChecked();
    expect(screen.getByTestId("type-save")).toBeDisabled();
    expect(screen.queryByTestId("type-notes")).not.toBeInTheDocument();
  });

  it("states the current type, and that the owner chose it when they did", () => {
    setup(fixtureAccount("card")); // a credit card the owner set
    expect(screen.getByTestId("type-dialog")).toHaveTextContent("Now: Credit card (set by you).");
  });

  it("sends only the type, then refreshes accounts and balances and reports that it left balances", async () => {
    const { account, onDone, invalidate } = setup();
    vi.mocked(accountsApi.updateAccount).mockResolvedValue({ ...account, type: "credit_card" });
    const user = userEvent.setup();

    await user.click(screen.getByTestId("type-option-credit_card"));
    await user.click(screen.getByTestId("type-save"));

    await waitFor(() => expect(onDone).toHaveBeenCalledWith("“Main” is now a credit card and no longer in balances."));
    expect(accountsApi.updateAccount).toHaveBeenCalledWith(account.id, { type: "credit_card" });
    const keys = invalidate.mock.calls.map(([filters]) => (filters as { queryKey: unknown }).queryKey);
    expect(keys).toEqual(expect.arrayContaining([["accounts"], ["balances"]]));
  });

  it("says a deposit account leaving balances keeps its entered balance", async () => {
    setup(); // Main has an entered balance
    await userEvent.setup().click(screen.getByTestId("type-option-unknown"));
    const notes = screen.getByTestId("type-notes");
    expect(notes).toHaveTextContent("It leaves balances, totals and charts straight away.");
    expect(notes).toHaveTextContent("The balance you entered is kept, in case you change it back.");
    expect(notes).toHaveTextContent("marks it as your choice");
  });

  it("does not promise a kept balance when there is none", async () => {
    setup(fixtureAccount("fresh"));
    await userEvent.setup().click(screen.getByTestId("type-option-credit_card"));
    expect(screen.getByTestId("type-notes")).not.toHaveTextContent("kept");
  });

  it("says a non-deposit account becoming a deposit account needs a balance, or has one again", async () => {
    const user = userEvent.setup();
    const { unmount } = setup(fixtureAccount("card")); // no entered balance
    await user.click(screen.getByTestId("type-option-deposit"));
    expect(screen.getByTestId("type-notes")).toHaveTextContent("It will show Anchor required until you enter a balance.");
    unmount();

    const anchored = fixtureAccount("main", { type: "credit_card" }); // had one, kept
    setup(anchored);
    await user.click(screen.getByTestId("type-option-deposit"));
    expect(screen.getByTestId("type-notes")).toHaveTextContent("Your entered balance of SGD 1,000.00 on 30 Jun 2026 applies again.");
  });

  it("only mentions that it is the owner's choice when moving between two non-deposit types", async () => {
    setup(fixtureAccount("card"));
    await userEvent.setup().click(screen.getByTestId("type-option-unknown"));
    const items = screen.getByTestId("type-notes").querySelectorAll("li");
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveTextContent("marks it as your choice");
  });

  it("switches Save back off when the choice is put back", async () => {
    setup();
    const user = userEvent.setup();
    await user.click(screen.getByTestId("type-option-unknown"));
    expect(screen.getByTestId("type-save")).toBeEnabled();
    await user.click(screen.getByTestId("type-option-deposit"));
    expect(screen.getByTestId("type-save")).toBeDisabled();
  });

  it("shows the API's refusal in the dialog and leaves it open", async () => {
    const { onDone } = setup();
    vi.mocked(accountsApi.updateAccount).mockRejectedValue(new ApiError(400, { error: "invalid_account_type", message: "x" }));
    const user = userEvent.setup();
    await user.click(screen.getByTestId("type-option-unknown"));
    await user.click(screen.getByTestId("type-save"));
    expect(await screen.findByTestId("type-error")).toHaveTextContent("Choose savings or current account, credit card, or other.");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("refreshes and reports when the account no longer exists", async () => {
    const { onDone } = setup();
    vi.mocked(accountsApi.updateAccount).mockRejectedValue(new ApiError(404, { error: "account_not_found", message: "x" }));
    const user = userEvent.setup();
    await user.click(screen.getByTestId("type-option-unknown"));
    await user.click(screen.getByTestId("type-save"));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("That account no longer exists; the list has been refreshed."));
  });
});
