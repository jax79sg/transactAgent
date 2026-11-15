import type { AccountType } from "../../api/types";
import { TYPE_BADGE } from "../../lib/balances";

// Issues #65-#70 (#68): an account's name says nothing about what kind of account it is ("OCBC Bank 5001" is a current
// account, "OCBC Bank 4002" a credit card). The words are the signal; the tint only helps the eye.
const TONE: Record<AccountType, string> = {
  deposit: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  credit_card: "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300",
  unknown: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
};

export function AccountTypeTag({ type, testId }: { type: AccountType; testId?: string }) {
  return (
    <span data-testid={testId} className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${TONE[type]}`}>
      {TYPE_BADGE[type]}
    </span>
  );
}
