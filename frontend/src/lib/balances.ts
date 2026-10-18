// Epic 13: the wording, dates, merge outcome and error messages of the Balances screens. Pure (no browser API except
// the clock passed in), so each rule can be tested on its own. The arithmetic itself is the API's; nothing here
// computes a balance.

import { ApiError } from "../api/client";
import type {
  AccountDTO,
  AccountType,
  AnchorResponse,
  BalancesResponse,
  BasisDTO,
  ExcludedAccountDTO,
  ExcludedReason,
  UnlinkedNoticeDTO,
} from "../api/types";
import { errorCode, formatDay, formatPeriod } from "./duplicates";
import { formatMoney } from "./money";

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export const monthName = (month: number): string => MONTH_NAMES[month - 1];

// ----------------------------------------------------------------------------------------------------------- dates

const pad = (n: number): string => String(n).padStart(2, "0");

/**
 * The browser's own calendar date as YYYY-MM-DD, built from the LOCAL year, month and day. Not `toISOString()`, which
 * is the UTC date and so yesterday's date in Singapore before 08:00. Only used to ask the first question; after the
 * first answer the API's `today` (in its reporting time zone) is the only "today".
 */
export function localToday(now: Pick<Date, "getFullYear" | "getMonth" | "getDate"> = new Date()): string {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** A calendar date moved by whole days, with no time zone anywhere in it. */
export function addDays(iso: string, days: number): string {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  const moved = new Date(Date.UTC(year, month - 1, day));
  moved.setUTCDate(moved.getUTCDate() + days);
  return moved.toISOString().slice(0, 10);
}

export const dayBefore = (iso: string): string => addDays(iso, -1);

/** "2026-10-18" -> "2026-10". */
export const monthOf = (iso: string): string => iso.slice(0, 7);

// ---------------------------------------------------------------------------------------------------------- wording

/** What a figure was worked from, in the owner's terms (AR-55). The table writes "From " in front of it. */
export function describeBasis(basis: Pick<BasisDTO, "source" | "date">): string {
  const day = formatDay(basis.date, true);
  return basis.source === "anchor" ? `your entered balance of ${day}` : `the statement closing balance of ${day}`;
}

/**
 * The heading over a lookup, from the response and never from the browser: a date, a past month (stating the day it
 * resolved to), or the current month so far.
 */
export function describeLookup(response: Pick<BalancesResponse, "resolvedDate" | "today" | "requestedMonth">): string {
  const resolved = formatDay(response.resolvedDate, true);
  if (response.requestedMonth === null) return `Balances at the end of ${resolved}`;
  const [year, month] = response.requestedMonth.split("-").map(Number);
  const label = `${monthName(month)} ${year}`;
  if (response.requestedMonth === monthOf(response.today)) {
    return `Balances for ${label} so far (to ${formatDay(response.resolvedDate, true)}, today)`;
  }
  return `Balances at the end of ${label} (${resolved})`;
}

// ------------------------------------------------------------------------------------------------------- accounts

type TypeFacts = Pick<AccountDTO, "type" | "typeSetByUser">;

/**
 * What a merge leaves as the kept account's type, so the preview can say it. Mirrors the API's rule (AR-54): the kept
 * account keeps its own type, unless its type was not chosen by the owner and the absorbed account's was, in which
 * case the owner's choice wins. `changed` is whether the type VALUE differs from what the kept account has now.
 */
export function mergeTypeOutcome(
  absorbed: TypeFacts,
  survivor: TypeFacts,
): { type: AccountType; typeSetByUser: boolean; changed: boolean } {
  if (!survivor.typeSetByUser && absorbed.typeSetByUser) {
    return { type: absorbed.type, typeSetByUser: true, changed: absorbed.type !== survivor.type };
  }
  return { type: survivor.type, typeSetByUser: survivor.typeSetByUser, changed: false };
}

/**
 * The next deposit account that has no balance entered, in the order given, skipping the ids in `skipIds` (the one
 * just saved and any saved earlier in the same run, whose entries a cached list may not show yet). Null when none.
 */
export function nextAccountNeedingBalance(accounts: readonly AccountDTO[], skipIds: readonly string[]): AccountDTO | null {
  return accounts.find((a) => a.canHaveAnchor && a.anchor === null && !skipIds.includes(a.id)) ?? null;
}

export const TYPE_LABELS: Record<AccountType, string> = {
  deposit: "Savings or current account",
  credit_card: "Credit card",
  unknown: "Other / type unknown",
};

/** "1 statement", "2 statements". */
export function pluralize(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** The type as a noun phrase, for a sentence ("\u201cB\u201d becomes a credit card ..."). */
export const TYPE_NOUNS: Record<AccountType, string> = {
  deposit: "a savings or current account",
  credit_card: "a credit card",
  unknown: "an account of unknown type",
};

/** "a", "a and b", "a, b and c". */
export function joinList(items: readonly string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** The notice for transactions linked to no account (AR-60): how many, from where, when, and the net per currency. */
export function describeUnlinked(notice: UnlinkedNoticeDTO): string {
  const one = notice.count === 1;
  const from = notice.bankNames.length > 0 ? ` from ${joinList(notice.bankNames)}` : "";
  const when =
    notice.earliestDate === notice.latestDate
      ? `dated ${formatDay(notice.earliestDate, true)}`
      : `dated ${formatPeriod(notice.earliestDate, notice.latestDate)}`;
  const net = joinList(notice.netByCurrency.map((entry) => formatMoney(entry.net, entry.currency)));
  return (
    `${pluralize(notice.count, "transaction", "transactions")}${from}, ${when} (net ${net}), ` +
    `${one ? "belongs" : "belong"} to no account, so ${one ? "it is" : "they are"} left out of every balance.`
  );
}

export const EXCLUSION_REASONS: Record<ExcludedReason, string> = {
  anchor_required: "anchor required",
  fx_unavailable: "no exchange rate",
};

/** Beside the total: every account left out of it, and why. Empty when none is. */
export function describeExclusions(excluded: readonly ExcludedAccountDTO[]): string {
  if (excluded.length === 0) return "";
  return `Not included: ${excluded.map((e) => `${e.name} (${EXCLUSION_REASONS[e.reason]})`).join(", ")}`;
}

// ----------------------------------------------------------------------------------------- outcomes of the writes

/** The status line after a balance is saved: says which account, the new figure, and the one it replaced. */
export function anchorSavedMessage(accountName: string, currency: string, response: AnchorResponse): string {
  const now = formatMoney(response.anchor.balance, currency);
  const day = formatDay(response.anchor.asOfDate, true);
  if (!response.previous) return `Saved ${now} for ${day} on \u201c${accountName}\u201d.`;
  const before = `${formatMoney(response.previous.balance, currency)} (${formatDay(response.previous.asOfDate, true)})`;
  return `Replaced ${before} with ${now} (${day}) on \u201c${accountName}\u201d.`;
}

export function typeChangedMessage(accountName: string, type: AccountType): string {
  const name = `\u201c${accountName}\u201d`;
  if (type === "deposit") return `${name} is now a savings or current account.`;
  if (type === "credit_card") return `${name} is now a credit card and no longer in balances.`;
  return `${name} is now marked other and no longer in balances.`;
}

/** What the type dialog tells the owner before they confirm (AR-52): the consequences, in words. */
export function typeChangeNotes(account: Pick<AccountDTO, "type" | "currency" | "anchor">, newType: AccountType): string[] {
  const notes: string[] = [];
  const wasDeposit = account.type === "deposit";
  const willBeDeposit = newType === "deposit";
  if (wasDeposit && !willBeDeposit) {
    notes.push(
      "It leaves balances, totals and charts straight away." +
        (account.anchor ? " The balance you entered is kept, in case you change it back." : ""),
    );
  } else if (!wasDeposit && willBeDeposit) {
    notes.push(
      account.anchor
        ? `Your entered balance of ${formatMoney(account.anchor.balance, account.currency)} on ${formatDay(account.anchor.asOfDate, true)} applies again.`
        : "It will show Anchor required until you enter a balance.",
    );
  }
  notes.push("Changing the type marks it as your choice, so later statements won't overwrite it.");
  return notes;
}

// ---------------------------------------------------------------------------------------------------------- errors

/** Every code the account and balance endpoints can refuse with (AR-64). A new code fails to compile until worded. */
export type BalanceErrorCode =
  | "account_not_found"
  | "invalid_anchor_value"
  | "anchor_date_in_future"
  | "anchor_date_out_of_range"
  | "not_a_deposit_account"
  | "nothing_to_change"
  | "invalid_account_name"
  | "invalid_account_type"
  | "merge_same_account"
  | "merge_currency_mismatch"
  | "merge_appear_together"
  | "merge_anchor_choice_required"
  | "merge_anchor_choice_invalid"
  | "date_or_month_required"
  | "date_in_future"
  | "month_in_future"
  | "invalid_date_range"
  | "range_too_large";

export const BALANCE_ERROR_MESSAGES: Record<BalanceErrorCode, string> = {
  account_not_found: "That account no longer exists; the list has been refreshed.",
  invalid_anchor_value: "Enter the balance as a number with at most two decimal places, for example 1,234.50.",
  anchor_date_in_future: "The date can't be after today.",
  anchor_date_out_of_range: "The date is too far back; dates before 1 Jan 2000 aren't supported.",
  not_a_deposit_account: "Only savings and current accounts have a balance. Change this account's type first.",
  nothing_to_change: "Nothing was changed.",
  invalid_account_name: "The name must be between 1 and 255 characters.",
  invalid_account_type: "Choose savings or current account, credit card, or other.",
  merge_same_account: "Choose a different account to merge into.",
  merge_currency_mismatch: "These accounts are in different currencies, so they can't be one account.",
  merge_appear_together:
    "These two accounts are listed together on one statement, so they are different accounts. If they look alike, rename them instead.",
  merge_anchor_choice_required: "Both accounts have a balance entered. Choose which one to keep.",
  merge_anchor_choice_invalid: "Choose the balance of one of these two accounts.",
  date_or_month_required: "Choose a date or a month.",
  date_in_future: "That is after today. Choose today or an earlier date.",
  month_in_future: "That is after today. Choose today or an earlier date.",
  invalid_date_range:
    "The start must be on or before the end, the end can't be after today, and dates before 2000 aren't supported.",
  range_too_large: "That range has too many points. Choose a shorter range or month-end points.",
};

function isBalanceErrorCode(code: string): code is BalanceErrorCode {
  return Object.prototype.hasOwnProperty.call(BALANCE_ERROR_MESSAGES, code);
}

/** Plain words for whatever went wrong, from the API's stable code; any other API error shows the server's own message. */
export function balanceErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Couldn't reach the server.";
  if (error.status === 422) return "That isn't a valid date."; // a malformed date is FastAPI's own 422, with no {error, message}
  if (error.status >= 500) return "The server had a problem. Please try again.";
  const code = error.body.error;
  if (isBalanceErrorCode(code)) return BALANCE_ERROR_MESSAGES[code];
  return error.body.message || "Something went wrong. Please try again.";
}

/** True when the account the user was working on is gone, so the dialog closes and the list refreshes. */
export function isAccountGone(error: unknown): boolean {
  return errorCode(error) === "account_not_found";
}
