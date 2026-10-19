// Probable Duplicate Statement Detection (Epic 14): the comparison page, opened from the Ingestion run results ("probable
// duplicate of ...") and from the Review panel's "View comparison". Shows two stored snapshots side by side so a person
// can be sure. Design: aidlc-docs/construction/frontend/functional-design/frontend-components.md.
//
// The page shows what was stored at detection time, so it is unchanged if the original is later changed or removed.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { getComparison, overrideSkippedFile } from "../api/duplicates";
import type { ComparisonSide, ComparisonState, DuplicateComparison } from "../api/types";
import { FlowAmount } from "../components/FlowAmount";
import { duplicateErrorMessage, formatPeriod, formatStatementLabel } from "../lib/duplicates";

const MARKER_TEXT = { also_on_other: "Also on the other statement", only_on_this_one: "Only on this one" } as const;

// The marker is always spelled out in words as well as tinted, so its meaning never depends on colour alone.
const MARKER_TINT = {
  also_on_other: "bg-emerald-50 dark:bg-emerald-950/30",
  only_on_this_one: "bg-amber-50 dark:bg-amber-950/30",
} as const;

function StateBanner({ comparison }: { comparison: DuplicateComparison }) {
  const text: Record<ComparisonState, string> = {
    skipped: "Skipped as a probable duplicate. It was not ingested.",
    removed: "Removed at your confirmation. The file is still in Google Drive.",
    ingest_at_next_run: "Will be ingested on the next ingestion run.",
    ingested_at_your_request: "Ingested at your request.",
    pair_pending: comparison.removalOffered
      ? "Two stored statements that look like the same statement. You can remove the duplicate from the Review page."
      : "Two stored statements that look like the same statement. Their sizes differ, so this is listed for information only.",
    pair_dismissed: "You dismissed this pair as not a duplicate.",
    pair_superseded: "This pair is no longer current.",
  };
  return (
    <div data-testid="comparison-banner" className="mb-3 rounded border border-slate-200 p-3 text-sm dark:border-slate-700">
      <p className="font-medium">{text[comparison.state]}</p>
      {comparison.state === "ingest_at_next_run" && (
        <p className="mt-1">
          <Link to="/ingestion" className="underline">
            Go to Ingestion
          </Link>{" "}
          to run it now.
        </p>
      )}
      {comparison.pairId && (
        <p className="mt-1">
          <Link to="/review" className="underline">
            Back to the Review page
          </Link>
        </p>
      )}
    </div>
  );
}

function SidePanel({ title, side, testId }: { title: string; side: ComparisonSide; testId: string }) {
  return (
    <section data-testid={testId} className="min-w-0 rounded border border-slate-200 p-3 dark:border-slate-700">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</h2>
      <p className="break-words text-sm font-medium">{formatStatementLabel(side.label)}</p>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {side.label.transactionCount} transaction{side.label.transactionCount === 1 ? "" : "s"}; showing the{" "}
        {side.rows.length} largest
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs text-slate-500 dark:text-slate-400">
              <th className="pr-2">Date</th>
              <th className="pr-2">Description</th>
              <th className="pr-2">Amount</th>
              <th className="hidden sm:table-cell">Match</th>
            </tr>
          </thead>
          <tbody>
            {side.rows.map((row) => (
              <tr key={row.rank} data-testid={`${testId}-row-${row.rank}`} className={MARKER_TINT[row.marker]}>
                <td className="whitespace-nowrap pr-2">{row.transactionDate}</td>
                <td className="pr-2">
                  {row.description}
                  {/* Phone width: a Match column would be pushed off-screen, so the marker is spelled out under the
                      description instead (the column below is hidden there). */}
                  <span className="block text-xs text-slate-500 dark:text-slate-400 sm:hidden">{MARKER_TEXT[row.marker]}</span>
                </td>
                <td className="whitespace-nowrap pr-2">
                  <FlowAmount outFlow={row.outFlow} inFlow={row.inFlow} /> {row.currency}
                </td>
                <td data-testid={`${testId}-marker-${row.rank}`} className="hidden text-xs sm:table-cell">
                  {MARKER_TEXT[row.marker]}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function OverrideAction({ comparison }: { comparison: DuplicateComparison }) {
  const queryClient = useQueryClient();
  const [warning, setWarning] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Bringing back a REMOVED copy has real consequences (its corrections are not restored), so it takes a second
  // click; overriding a merely skipped file is recoverable and takes one.
  const needsSecondClick = comparison.state === "removed";

  const mutation = useMutation({
    mutationFn: () => overrideSkippedFile(comparison.id),
    onSuccess: (result) => {
      setError(null);
      setWarning(false);
      setNote(result.note);
      queryClient.invalidateQueries({ queryKey: ["duplicates"] });
    },
    onError: (e) => setError(duplicateErrorMessage(e)),
  });

  if (!comparison.canOverride) {
    return note ? (
      <p data-testid="override-note" className="text-sm text-slate-600 dark:text-slate-300">
        {note}
      </p>
    ) : null;
  }

  return (
    <div className="mb-3">
      {!warning ? (
        <button
          data-testid="override-button"
          onClick={() => (needsSecondClick ? setWarning(true) : mutation.mutate())}
          disabled={mutation.isPending}
          className="rounded bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
        >
          Not a duplicate -- ingest it
        </button>
      ) : (
        <div data-testid="override-warning" className="rounded border border-amber-400 p-3 text-sm dark:border-amber-600">
          <p>
            This file will be ingested on the next run. The manual corrections that sat on this copy are not
            restored.
          </p>
          <div className="mt-2 flex gap-3">
            <button
              data-testid="override-confirm"
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              className="rounded bg-slate-900 px-3 py-1 text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
            >
              Ingest it
            </button>
            <button onClick={() => setWarning(false)} className="text-slate-600 dark:text-slate-300">
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && (
        <p data-testid="override-error" className="mt-1 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}

export function ComparisonPage() {
  const { comparisonId = "" } = useParams();
  const navigate = useNavigate();
  const { data, isPending, isError } = useQuery({
    queryKey: ["duplicates", "comparison", comparisonId],
    queryFn: () => getComparison(comparisonId),
    retry: false,
  });

  const goBack = () => (window.history.length > 1 ? navigate(-1) : navigate("/review"));

  if (isPending) return <p className="text-sm text-slate-500 dark:text-slate-400">Loading...</p>;
  if (isError || !data) {
    return (
      <div>
        <button onClick={goBack} className="mb-3 text-sm underline">
          Back
        </button>
        <p data-testid="comparison-not-found" className="text-sm text-slate-600 dark:text-slate-300">
          That comparison could not be found.
        </p>
      </div>
    );
  }

  // For a skipped or removed FILE the sides are "this file" and "the statement it matches"; for two stored statements
  // they are simply the earlier- and later-ingested.
  const titles =
    data.thisFileSide === "later"
      ? { earlier: "The statement it matches", later: "This file" }
      : data.thisFileSide === "earlier"
        ? { earlier: "This file", later: "The statement it matches" }
        : { earlier: "Earlier ingested", later: "Later ingested" };

  return (
    <div>
      <button data-testid="comparison-back" onClick={goBack} className="mb-3 text-sm underline">
        Back
      </button>
      <h1 className="mb-3 text-xl font-semibold">Probable duplicate comparison</h1>

      <StateBanner comparison={data} />
      <OverrideAction comparison={data} />

      <p data-testid="comparison-reason" className="mb-2 text-sm">
        {data.reason}
      </p>
      <p data-testid="comparison-figures" className="mb-3 text-sm text-slate-600 dark:text-slate-300">
        {data.earlier.label.transactionCount} and {data.later.label.transactionCount} transactions
        ({formatPeriod(data.earlier.label.periodStart, data.earlier.label.periodEnd)} and{" "}
        {formatPeriod(data.later.label.periodStart, data.later.label.periodEnd)}); {data.matchedCount} matched.
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        <SidePanel title={titles.earlier} side={data.earlier} testId="comparison-earlier" />
        <SidePanel title={titles.later} side={data.later} testId="comparison-later" />
      </div>
    </div>
  );
}
