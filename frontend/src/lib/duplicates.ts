// Probable Duplicate Statement Detection (Epic 14): one place that formats a statement label and a period, and
// turns the API's stable error codes into plain sentences, so the Ingestion results, the Review panel and the
// comparison page read the same.

import { ApiError } from "../api/client";
import type { StatementLabel } from "../api/types";

// Written out rather than taken from the browser's locale, so the same text appears on every machine and in tests.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "2026-06-02" -> { year: 2026, month: 6, day: 2 }. Parsed from the text, never through Date, so the user's
// time zone cannot move a statement date by a day.
function parseDate(iso: string): { year: number; month: number; day: number } {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  return { year, month, day };
}

function formatDay(iso: string, withYear: boolean): string {
  const { year, month, day } = parseDate(iso);
  return `${day} ${MONTHS[month - 1]}${withYear ? ` ${year}` : ""}`;
}

/** "2 Jun to 30 Jun 2026" within one year, "28 Dec 2025 to 3 Jan 2026" across two. */
export function formatPeriod(start: string, end: string): string {
  if (parseDate(start).year === parseDate(end).year) {
    return `${formatDay(start, false)} to ${formatDay(end, true)}`;
  }
  return `${formatDay(start, true)} to ${formatDay(end, true)}`;
}

/** "<file name> (<bank>, <period>)"; "<bank> (<period>)" without a file name; "a statement (<period>)" with neither (A-PD-3). */
export function formatStatementLabel(
  label: Pick<StatementLabel, "fileName" | "bankName" | "periodStart" | "periodEnd">,
): string {
  const period = formatPeriod(label.periodStart, label.periodEnd);
  if (label.fileName) {
    return label.bankName ? `${label.fileName} (${label.bankName}, ${period})` : `${label.fileName} (${period})`;
  }
  return `${label.bankName ?? "a statement"} (${period})`;
}

// Errors after which what the user was looking at is out of date: the confirmation closes, the list refreshes, and
// nothing was deleted.
export const STALE_ACTION_ERRORS = new Set([
  "confirmation_out_of_date",
  "pair_not_pending",
  "removal_not_offered",
  "removal_already_requested",
  "statement_missing",
]);

export function errorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.body.error : null;
}

export function duplicateErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something went wrong. Please try again.";
  switch (error.body.error) {
    case "pair_not_pending":
      return "This pair has already been decided.";
    case "removal_not_offered":
      return "Removal isn't offered for this pair, because the two statements differ in size.";
    case "removal_already_requested":
      return "A removal for this pair is already in progress.";
    case "statement_missing":
      return "One of these statements no longer exists, so nothing was removed.";
    case "not_a_skipped_file":
      return "This comparison has no skipped file to override.";
    case "confirmation_out_of_date":
      // The server's sentence names exactly what changed (the copy, or the correction counts) and ends "Please review again."
      return error.body.message;
    default:
      return error.body.message || "Something went wrong. Please try again.";
  }
}
