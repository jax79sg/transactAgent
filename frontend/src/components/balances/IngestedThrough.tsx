import type { UnlinkedNoticeDTO } from "../../api/types";
import { describeUnlinked } from "../../lib/balances";
import { formatDay } from "../../lib/duplicates";

// Epic 13 (FR-AB-14): every lookup says how far the transactions go, so a balance asked for after that date is not
// mistaken for a live bank balance. Later than the data, the line turns amber and offers the last date that is real.
export function IngestedThrough({
  resolvedDate,
  ingestedThroughDate,
  onJumpTo,
}: {
  resolvedDate: string;
  ingestedThroughDate: string | null;
  onJumpTo: (date: string) => void;
}) {
  if (ingestedThroughDate === null) {
    return (
      <p data-testid="ingested-through" className="text-sm text-slate-600 dark:text-slate-300">
        No transactions have been ingested yet.
      </p>
    );
  }
  const later = resolvedDate > ingestedThroughDate;
  const shown = formatDay(ingestedThroughDate, true);
  return (
    <p
      data-testid="ingested-through"
      className={
        later
          ? "rounded bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-300"
          : "text-sm text-slate-600 dark:text-slate-300"
      }
    >
      Transactions are ingested through {shown}.
      {later && (
        <>
          {" "}
          This date is later, so the figures don&apos;t include any activity after it.{" "}
          <button
            type="button"
            data-testid="ingested-through-jump"
            onClick={() => onJumpTo(ingestedThroughDate)}
            className="underline"
          >
            Show {shown}
          </button>
        </>
      )}
    </p>
  );
}

// Epic 13 (Question 6 = A, AR-60): transactions linked to no account belong to no balance. Information only.
export function UnlinkedNotice({ notice }: { notice: UnlinkedNoticeDTO | null }) {
  if (notice === null) return null;
  return (
    <p data-testid="unlinked-notice" className="rounded bg-slate-100 px-3 py-2 text-sm dark:bg-slate-800 dark:text-slate-200">
      {describeUnlinked(notice)}
    </p>
  );
}
