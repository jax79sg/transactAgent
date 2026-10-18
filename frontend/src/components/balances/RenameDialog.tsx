import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { updateAccount } from "../../api/accounts";
import type { AccountDTO } from "../../api/types";
import { balanceErrorMessage, isAccountGone } from "../../lib/balances";
import { CANCEL_CLASS, DialogFrame, ERROR_CLASS, FIELD_CLASS, PRIMARY_CLASS } from "./DialogFrame";
import { useRefreshBalanceData, WRITE_MUTATION_KEY } from "./queries";

const MAX_NAME = 255;

// Epic 13 (US-13.2): rename an account. Names need not be unique (the same-named accounts in the data are exactly what
// this exists to tell apart), so nothing here checks for duplicates. Sends PATCH with the name only.
export function RenameDialog({
  account,
  onClose,
  onDone,
}: {
  account: AccountDTO;
  onClose: () => void;
  /** Called with the sentence for the status line, after the list has been refreshed. */
  onDone: (message: string) => void;
}) {
  const [name, setName] = useState(account.name);
  const refresh = useRefreshBalanceData();
  const trimmed = name.trim();

  const mutation = useMutation({
    mutationKey: WRITE_MUTATION_KEY,
    mutationFn: () => updateAccount(account.id, { name: trimmed }),
    onSuccess: async () => {
      await refresh();
      onDone(`Renamed “${account.name}” to “${trimmed}”.`);
    },
    onError: async (error) => {
      if (isAccountGone(error)) {
        await refresh();
        onDone(balanceErrorMessage(error));
      }
    },
  });

  const unchanged = trimmed === account.name;
  const invalid = trimmed.length === 0 || trimmed.length > MAX_NAME;

  return (
    <DialogFrame
      testId="rename-dialog"
      title={`Rename “${account.name}”`}
      description={`${account.bankName}${account.accountIdentifier ? ` ${account.accountIdentifier}` : ""}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" data-testid="rename-cancel" onClick={onClose} className={CANCEL_CLASS}>
            Cancel
          </button>
          <button
            type="submit"
            form="rename-form"
            data-testid="rename-save"
            disabled={mutation.isPending || invalid || unchanged}
            className={PRIMARY_CLASS}
          >
            Save
          </button>
        </>
      }
    >
      <form
        id="rename-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!invalid && !unchanged && !mutation.isPending) mutation.mutate();
        }}
      >
        <label className="block text-sm">
          Name
          <input
            data-testid="rename-input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoFocus
            className={`mt-1 ${FIELD_CLASS}`}
          />
        </label>
        <p data-testid="rename-count" className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {trimmed.length}/{MAX_NAME}
        </p>
        {mutation.isError && !isAccountGone(mutation.error) && (
          <p data-testid="rename-error" className={ERROR_CLASS}>
            {balanceErrorMessage(mutation.error)}
          </p>
        )}
      </form>
    </DialogFrame>
  );
}
