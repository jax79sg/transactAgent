import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as accountsApi from "../src/api/accounts";
import { ApiError } from "../src/api/client";
import { RenameDialog } from "../src/components/balances/RenameDialog";
import { renderWithQueryClient } from "./balanceTestUtils";
import { fixtureAccount } from "./balancesFixtures";

vi.mock("../src/api/accounts");

function setup(account = fixtureAccount("main")) {
  const onClose = vi.fn();
  const onDone = vi.fn();
  const view = renderWithQueryClient(<RenameDialog account={account} onClose={onClose} onDone={onDone} />);
  const invalidate = vi.spyOn(view.queryClient, "invalidateQueries");
  return { ...view, account, onClose, onDone, invalidate };
}

async function typeName(text: string) {
  const user = userEvent.setup();
  const input = screen.getByTestId("rename-input");
  await user.clear(input);
  if (text) await user.type(input, text);
  return user;
}

describe("RenameDialog", () => {
  it("opens on the current name with Save off, since nothing has changed", () => {
    setup();
    expect(screen.getByTestId("rename-input")).toHaveValue("Main");
    expect(screen.getByTestId("rename-count")).toHaveTextContent("4/255");
    expect(screen.getByTestId("rename-save")).toBeDisabled();
  });

  it("sends only the trimmed name, then refreshes accounts and balances together and reports", async () => {
    const { account, onDone, invalidate } = setup();
    vi.mocked(accountsApi.updateAccount).mockResolvedValue({ ...account, name: "Holiday fund" });
    const user = await typeName("  Holiday fund  ");

    await user.click(screen.getByTestId("rename-save"));

    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Renamed “Main” to “Holiday fund”."));
    expect(accountsApi.updateAccount).toHaveBeenCalledWith(account.id, { name: "Holiday fund" });
    const keys = invalidate.mock.calls.map(([filters]) => (filters as { queryKey: unknown }).queryKey);
    expect(keys).toEqual(expect.arrayContaining([["accounts"], ["balances"]]));
  });

  it("submits with Enter", async () => {
    const { account, onDone } = setup();
    vi.mocked(accountsApi.updateAccount).mockResolvedValue({ ...account, name: "Renamed" });
    const user = await typeName("Renamed");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("keeps Save off for an empty name, a blank name, an unchanged name (after trimming) and a name over 255", async () => {
    setup();
    await typeName("");
    expect(screen.getByTestId("rename-save")).toBeDisabled();
    const user = await typeName("   ");
    expect(screen.getByTestId("rename-save")).toBeDisabled();
    await user.clear(screen.getByTestId("rename-input"));
    await user.type(screen.getByTestId("rename-input"), "  Main ");
    expect(screen.getByTestId("rename-save")).toBeDisabled();
    await user.clear(screen.getByTestId("rename-input"));
    await user.click(screen.getByTestId("rename-input"));
    await user.paste("x".repeat(256));
    expect(screen.getByTestId("rename-count")).toHaveTextContent("256/255");
    expect(screen.getByTestId("rename-save")).toBeDisabled();
  });

  it("accepts exactly 255 characters", async () => {
    setup();
    const user = await typeName("");
    await user.click(screen.getByTestId("rename-input"));
    await user.paste("y".repeat(255));
    expect(screen.getByTestId("rename-save")).toBeEnabled();
  });

  it("does not insist on a unique name (the same-named accounts are what this is for)", async () => {
    const { account, onDone } = setup(fixtureAccount("fresh"));
    vi.mocked(accountsApi.updateAccount).mockResolvedValue({ ...account, name: "Main" });
    const user = await typeName("Main"); // another account is already called Main
    await user.click(screen.getByTestId("rename-save"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("shows the API's refusal in the dialog and leaves it open, nothing reported", async () => {
    const { account, onDone, invalidate } = setup();
    vi.mocked(accountsApi.updateAccount).mockRejectedValue(new ApiError(400, { error: "invalid_account_name", message: "x" }));
    const user = await typeName("New name");
    await user.click(screen.getByTestId("rename-save"));

    expect(await screen.findByTestId("rename-error")).toHaveTextContent("The name must be between 1 and 255 characters.");
    expect(onDone).not.toHaveBeenCalled();
    expect(invalidate).not.toHaveBeenCalled();
    expect(screen.getByTestId("rename-dialog")).toBeInTheDocument();
    expect(accountsApi.updateAccount).toHaveBeenCalledWith(account.id, { name: "New name" });
  });

  it("refreshes and reports when the account no longer exists, without an error box", async () => {
    const { onDone, invalidate } = setup();
    vi.mocked(accountsApi.updateAccount).mockRejectedValue(new ApiError(404, { error: "account_not_found", message: "x" }));
    const user = await typeName("New name");
    await user.click(screen.getByTestId("rename-save"));

    await waitFor(() => expect(onDone).toHaveBeenCalledWith("That account no longer exists; the list has been refreshed."));
    expect(invalidate).toHaveBeenCalled();
    expect(screen.queryByTestId("rename-error")).not.toBeInTheDocument();
  });

  it("switches Save off while the request is in flight, so it cannot be sent twice", async () => {
    const { account } = setup();
    let finish: (value: unknown) => void = () => {};
    vi.mocked(accountsApi.updateAccount).mockReturnValue(new Promise((resolve) => (finish = resolve)) as never);
    const user = await typeName("Slow");
    await user.click(screen.getByTestId("rename-save"));
    await waitFor(() => expect(screen.getByTestId("rename-save")).toBeDisabled());
    await user.keyboard("{Enter}");
    expect(accountsApi.updateAccount).toHaveBeenCalledTimes(1);
    finish({ ...account, name: "Slow" });
  });

  it("closes without sending anything on Cancel", async () => {
    const { onClose } = setup();
    const user = await typeName("Something else");
    await user.click(screen.getByTestId("rename-cancel"));
    expect(onClose).toHaveBeenCalled();
    expect(accountsApi.updateAccount).not.toHaveBeenCalled();
  });
});
