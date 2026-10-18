import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { setAnchor } from "../../api/accounts";
import type { AccountDTO, AnchorResponse } from "../../api/types";
import { balanceErrorMessage, isAccountGone } from "../../lib/balances";
import { formatDay } from "../../lib/duplicates";
import { formatMoney, parseAmountInput } from "../../lib/money";
import { CANCEL_CLASS, DialogFrame, ERROR_CLASS, FIELD_CLASS, PRIMARY_CLASS } from "./DialogFrame";
import { useRefreshBalanceData, WRITE_MUTATION_KEY } from "./queries";

const EARLIEST_DATE = "2000-01-01";

const AMOUNT_PROBLEMS = {
  empty: "Enter the balance.",
  not_a_number: "That isn't a number. Use digits, for example 1,234.50.",
  too_many_decimals: "Use at most two decimal places; the amount isn't rounded for you.",
} as const;

export interface BalanceSaveResult {
  account: AccountDTO;
  response: AnchorResponse;
  /** True when the owner chose "Save and next account". */
  saveAndNext: boolean;
}

/** The first problem with what was typed, in plain words, or null. Nothing is sent while there is one. */
function problemWith(balanceText: string, dateText: string, maxDate: string): string | null {
  const parsed = parseAmountInput(balanceText);
  if (!parsed.ok) return AMOUNT_PROBLEMS[parsed.reason];
  if (dateText === "") return "Choose the date this balance applies to.";
  if (dateText > maxDate) return "The date can't be after today.";
  if (dateText < EARLIEST_DATE) return "Dates before 1 Jan 2000 aren't supported.";
  return null;
}

// Epic 13 (US-13.3): enter or replace an account's single known balance. The balance is in the account's own currency
// and is the END-OF-DAY balance of the date, which the dialog says; when one exists its value is shown so the owner
// sees what is being replaced. A run of accounts is quick: "Save and next account" (offered while another deposit
// account still needs a balance) saves, and the parent opens the next one with the date carried over.
export function BalanceDialog({
  account,
  defaultDate,
  maxDate,
  canSaveAndNext,
  onClose,
  onSaved,
  onGone,
}: {
  account: AccountDTO;
  defaultDate: string;
  /** The API's "today": the latest date accepted. */
  maxDate: string;
  canSaveAndNext: boolean;
  onClose: () => void;
  onSaved: (result: BalanceSaveResult) => void;
  /** The account no longer exists: the list was refreshed and the sentence is for the status line. */
  onGone: (message: string) => void;
}) {
  const [balanceText, setBalanceText] = useState("");
  const [dateText, setDateText] = useState(defaultDate);
  const [validation, setValidation] = useState<string | null>(null);
  const refresh = useRefreshBalanceData();

  const mutation = useMutation({
    mutationKey: WRITE_MUTATION_KEY,
    mutationFn: (variables: { balance: string; asOfDate: string; saveAndNext: boolean }) =>
      setAnchor(account.id, { balance: variables.balance, asOfDate: variables.asOfDate }),
    onSuccess: async (response, variables) => {
      await refresh();
      onSaved({ account, response, saveAndNext: variables.saveAndNext });
    },
    onError: async (error) => {
      if (isAccountGone(error)) {
        await refresh();
        onGone(balanceErrorMessage(error));
      }
    },
  });

  function submit(saveAndNext: boolean) {
    if (mutation.isPending) return;
    const problem = problemWith(balanceText, dateText, maxDate);
    setValidation(problem);
    if (problem) return;
    const parsed = parseAmountInput(balanceText);
    if (!parsed.ok) return;
    mutation.mutate({ balance: parsed.value, asOfDate: dateText, saveAndNext });
  }

  const replacing = account.anchor !== null;
  const shownError = validation ?? (mutation.isError && !isAccountGone(mutation.error) ? balanceErrorMessage(mutation.error) : null);

  return (
    <DialogFrame
      testId="balance-dialog"
      title={`${replacing ? "Replace" : "Set"} the balance of “${account.name}”`}
      description={`In ${account.currency}. Enter the balance at the end of that day, after that day's transactions. Use a figure from your banking app or a statement.`}
      onClose={onClose}
      footer={
        <>
          <button type="button" data-testid="balance-cancel" onClick={onClose} className={CANCEL_CLASS}>
            Cancel
          </button>
          {canSaveAndNext && (
            <button
              type="button"
              data-testid="balance-save-next"
              disabled={mutation.isPending}
              onClick={() => submit(true)}
              className="min-h-[40px] rounded border border-slate-300 px-3 py-1 disabled:opacity-50 dark:border-slate-600"
            >
              Save and next account
            </button>
          )}
          <button type="submit" form="balance-form" data-testid="balance-save" disabled={mutation.isPending} className={PRIMARY_CLASS}>
            {replacing ? "Replace balance" : "Save balance"}
          </button>
        </>
      }
    >
      {account.anchor && (
        <p data-testid="balance-previous" className="mb-3 rounded bg-slate-100 px-3 py-2 text-sm dark:bg-slate-900">
          Currently {formatMoney(account.anchor.balance, account.currency)} on {formatDay(account.anchor.asOfDate, true)}.
          Saving replaces it.
        </p>
      )}
      {/* noValidate: the date input has min/max, and the browser's own validation would swallow the submit with its
          own bubble; the dialog checks everything itself, in one set of words (and so does the same in every browser). */}
      <form
        id="balance-form"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          submit(false);
        }}
      >
        <label className="block text-sm">
          Balance ({account.currency})
          <input
            data-testid="balance-input"
            inputMode="decimal"
            autoComplete="off"
            value={balanceText}
            onChange={(event) => {
              setBalanceText(event.target.value);
              setValidation(null);
            }}
            autoFocus
            className={`mt-1 ${FIELD_CLASS}`}
          />
        </label>
        <label className="mt-3 block text-sm">
          Balance on
          <input
            data-testid="balance-date-input"
            type="date"
            min={EARLIEST_DATE}
            max={maxDate}
            value={dateText}
            onChange={(event) => {
              setDateText(event.target.value);
              setValidation(null);
            }}
            className={`mt-1 ${FIELD_CLASS}`}
          />
        </label>
        {/* With two fields, Enter submits only when the form holds a submit button; the visible one is in the dialog's
            footer, outside the form element, so a hidden default one sits here. */}
        <button type="submit" hidden tabIndex={-1} aria-hidden="true" />
        {shownError && (
          <p data-testid="balance-error" role="alert" className={ERROR_CLASS}>
            {shownError}
          </p>
        )}
      </form>
    </DialogFrame>
  );
}
