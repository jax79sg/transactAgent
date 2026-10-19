import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { updateAccount } from "../../api/accounts";
import type { AccountDTO, AccountType } from "../../api/types";
import { balanceErrorMessage, isAccountGone, TYPE_LABELS, typeChangedMessage, typeChangeNotes } from "../../lib/balances";
import { CANCEL_CLASS, DialogFrame, ERROR_CLASS, PRIMARY_CLASS } from "./DialogFrame";
import { useRefreshBalanceData, WRITE_MUTATION_KEY } from "./queries";

const OPTIONS: { type: AccountType; description: string }[] = [
  { type: "deposit", description: "Included in balances." },
  { type: "credit_card", description: "Never part of balances." },
  { type: "unknown", description: "Left out of balances until you decide." },
];

// Epic 13 (US-13.2): correct an account's type. Says what will happen before the owner confirms: leaving "deposit"
// removes the account from balances at once but keeps any balance entered; becoming "deposit" shows "Anchor required"
// until one exists. Sends PATCH with the type only.
export function ChangeTypeDialog({
  account,
  onClose,
  onDone,
}: {
  account: AccountDTO;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [type, setType] = useState<AccountType>(account.type);
  const refresh = useRefreshBalanceData();

  const mutation = useMutation({
    mutationKey: WRITE_MUTATION_KEY,
    mutationFn: () => updateAccount(account.id, { type }),
    onSuccess: async () => {
      await refresh();
      onDone(typeChangedMessage(account.name, type));
    },
    onError: async (error) => {
      if (isAccountGone(error)) {
        await refresh();
        onDone(balanceErrorMessage(error));
      }
    },
  });

  const unchanged = type === account.type;

  return (
    <DialogFrame
      testId="type-dialog"
      title={`Change the type of “${account.name}”`}
      description={`Now: ${TYPE_LABELS[account.type]}${account.typeSetByUser ? " (set by you)" : ""}.`}
      onClose={onClose}
      footer={
        <>
          <button type="button" data-testid="type-cancel" onClick={onClose} className={CANCEL_CLASS}>
            Cancel
          </button>
          <button
            type="button"
            data-testid="type-save"
            disabled={mutation.isPending || unchanged}
            onClick={() => mutation.mutate()}
            className={PRIMARY_CLASS}
          >
            Save
          </button>
        </>
      }
    >
      <fieldset>
        <legend className="sr-only">Account type</legend>
        {OPTIONS.map((option) => (
          <label key={option.type} className="mb-2 flex cursor-pointer items-start gap-2 text-sm">
            <input
              type="radio"
              name="account-type"
              data-testid={`type-option-${option.type}`}
              checked={type === option.type}
              onChange={() => setType(option.type)}
              className="mt-1"
            />
            <span>
              <span className="font-medium">{TYPE_LABELS[option.type]}</span>: {option.description}
            </span>
          </label>
        ))}
      </fieldset>
      {!unchanged && (
        <ul data-testid="type-notes" className="mt-2 list-disc pl-5 text-sm text-slate-600 dark:text-slate-300">
          {typeChangeNotes(account, type).map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      {mutation.isError && !isAccountGone(mutation.error) && (
        <p data-testid="type-error" className={ERROR_CLASS}>
          {balanceErrorMessage(mutation.error)}
        </p>
      )}
    </DialogFrame>
  );
}
