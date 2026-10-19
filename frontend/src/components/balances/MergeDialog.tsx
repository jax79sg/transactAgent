import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { mergeAccounts } from "../../api/accounts";
import type { AccountDTO } from "../../api/types";
import { balanceErrorMessage, isAccountGone, mergeTypeOutcome, pluralize, TYPE_NOUNS } from "../../lib/balances";
import { formatDay } from "../../lib/duplicates";
import { formatMoney } from "../../lib/money";
import { CANCEL_CLASS, DANGER_CLASS, DialogFrame, ERROR_CLASS, FIELD_CLASS } from "./DialogFrame";
import { useRefreshBalanceData, WRITE_MUTATION_KEY } from "./queries";

const quoted = (name: string): string => `“${name}”`;

function optionLabel(account: AccountDTO): string {
  const identifier = account.accountIdentifier ? ` ${account.accountIdentifier}` : "";
  return `${account.name} · ${account.bankName}${identifier} · ${pluralize(account.statementCount, "statement", "statements")}`;
}

function anchorText(account: AccountDTO): string {
  return account.anchor
    ? `${formatMoney(account.anchor.balance, account.currency)} on ${formatDay(account.anchor.asOfDate, true)}`
    : "";
}

// Epic 13 (US-13.2, FR-AB-3): merge the account the dialog was opened on (the one that will DISAPPEAR) into another.
// Only accounts in the same currency are offered (an account has one currency). The preview says, in words, what will
// happen, including a change of type; when both accounts have a balance entered the owner must choose which to keep,
// with nothing preselected, so neither is dropped silently. The API makes the merge all-or-nothing, and its refusals
// (two accounts listed on one statement, a missing choice, ...) are worded here and leave the dialog open.
export function MergeDialog({
  absorbed,
  accounts,
  onClose,
  onDone,
}: {
  absorbed: AccountDTO;
  accounts: readonly AccountDTO[];
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [targetId, setTargetId] = useState("");
  const [keepFrom, setKeepFrom] = useState<string | null>(null);
  const refresh = useRefreshBalanceData();

  const candidates = accounts.filter((a) => a.id !== absorbed.id && a.currency === absorbed.currency);
  const survivor = candidates.find((a) => a.id === targetId) ?? null;
  const bothHaveBalances = survivor !== null && survivor.anchor !== null && absorbed.anchor !== null;
  const ready = survivor !== null && (!bothHaveBalances || keepFrom !== null);

  const mutation = useMutation({
    mutationKey: WRITE_MUTATION_KEY,
    mutationFn: (variables: { survivorId: string; keepAnchorFrom: string | null }) =>
      mergeAccounts(variables.survivorId, {
        absorbedAccountId: absorbed.id,
        ...(variables.keepAnchorFrom ? { keepAnchorFrom: variables.keepAnchorFrom } : {}),
      }),
    onSuccess: async () => {
      await refresh();
      onDone(`Merged ${quoted(absorbed.name)} into ${quoted(survivor?.name ?? "the other account")}.`);
    },
    onError: async (error) => {
      if (isAccountGone(error)) {
        await refresh();
        onDone(balanceErrorMessage(error));
      }
    },
  });

  const typeOutcome = survivor ? mergeTypeOutcome(absorbed, survivor) : null;

  return (
    <DialogFrame
      testId="merge-dialog"
      title={`Merge ${quoted(absorbed.name)} into another account`}
      description={`${quoted(absorbed.name)} will disappear from the list. Choose the account that keeps everything.`}
      onClose={onClose}
      footer={
        <>
          <button type="button" data-testid="merge-cancel" onClick={onClose} className={CANCEL_CLASS}>
            Cancel
          </button>
          <button
            type="button"
            data-testid="merge-confirm"
            disabled={!ready || mutation.isPending}
            onClick={() => survivor && mutation.mutate({ survivorId: survivor.id, keepAnchorFrom: bothHaveBalances ? keepFrom : null })}
            className={DANGER_CLASS}
          >
            Merge
          </button>
        </>
      }
    >
      {candidates.length === 0 ? (
        <p data-testid="merge-no-candidates" className="text-sm">
          There is no other {absorbed.currency} account to merge into.
        </p>
      ) : (
        <label className="block text-sm">
          Account to keep
          <select
            data-testid="merge-target-select"
            value={targetId}
            onChange={(event) => {
              setTargetId(event.target.value);
              setKeepFrom(null);
            }}
            className={`mt-1 ${FIELD_CLASS}`}
          >
            <option value="">Choose the account to keep</option>
            {candidates.map((account) => (
              <option key={account.id} value={account.id}>
                {optionLabel(account)}
              </option>
            ))}
          </select>
        </label>
      )}

      {survivor && typeOutcome && (
        <div data-testid="merge-preview" className="mt-3 text-sm">
          <ul className="list-disc pl-5">
            <li>
              All {pluralize(absorbed.statementCount, "statement", "statements")} and{" "}
              {pluralize(absorbed.transactionCount, "transaction", "transactions")} of {quoted(absorbed.name)} will count
              under {quoted(survivor.name)}.
            </li>
            <li>
              {quoted(absorbed.name)} disappears from the list; {quoted(survivor.name)} keeps its name.
            </li>
            <li>Later statements that match {quoted(absorbed.name)} will be filed under {quoted(survivor.name)}.</li>
            {typeOutcome.changed && (
              <li data-testid="merge-type-change">
                {quoted(survivor.name)} becomes {TYPE_NOUNS[typeOutcome.type]} because you set that type on{" "}
                {quoted(absorbed.name)}.
              </li>
            )}
            {!bothHaveBalances && (survivor.anchor || absorbed.anchor) && (
              <li data-testid="merge-anchor-kept">
                The balance entered for {quoted((survivor.anchor ? survivor : absorbed).name)} (
                {anchorText(survivor.anchor ? survivor : absorbed)}) will be kept.
              </li>
            )}
            <li className="font-medium">This can&apos;t be undone.</li>
          </ul>

          {bothHaveBalances && (
            <fieldset data-testid="merge-keep-choice" className="mt-3">
              <legend className="font-medium">Both have a balance entered. Which one do you keep?</legend>
              {[survivor, absorbed].map((account) => (
                <label key={account.id} className="mt-1 flex cursor-pointer items-start gap-2">
                  <input
                    type="radio"
                    name="keep-balance"
                    data-testid={`merge-keep-${account.id}`}
                    checked={keepFrom === account.id}
                    onChange={() => setKeepFrom(account.id)}
                    className="mt-1"
                  />
                  <span>
                    {quoted(account.name)}: {anchorText(account)}
                  </span>
                </label>
              ))}
            </fieldset>
          )}
        </div>
      )}

      {mutation.isError && !isAccountGone(mutation.error) && (
        <p data-testid="merge-error" role="alert" className={ERROR_CLASS}>
          {balanceErrorMessage(mutation.error)}
        </p>
      )}
    </DialogFrame>
  );
}
