// Probable Duplicate Statement Detection (Epic 14): the "Probable duplicate statements" panel on the Review page.
// Design: aidlc-docs/construction/frontend/functional-design/frontend-components.md.
//
// The panel only DISPLAYS what the Ingestion Worker found and RECORDS the user's decisions: which copy is proposed
// for removal, and whether removal is offered at all (a pair of clearly different sizes is information only), both
// come from the server and are never worked out here.

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { Link } from "react-router-dom";

import { dismissPair, getScanStatus, listPairs, requestRecheck, requestRemoval } from "../api/duplicates";
import type { DuplicatePair, DuplicatePairPage, RemovalJobStatus, RemovalPreview } from "../api/types";
import { duplicateErrorMessage, errorCode, formatStatementLabel, STALE_ACTION_ERRORS } from "../lib/duplicates";

const PAGE_SIZE = 20;
// The same cadence as the Ingestion page's active-run poll: the user has just asked for a removal and is waiting.
const IN_FLIGHT_POLL_INTERVAL_MS = 3000;
const IN_FLIGHT_STATUSES: RemovalJobStatus[] = ["queued", "running", "embeddings_pending"];

function isInFlight(pair: DuplicatePair): boolean {
  return pair.removal !== null && IN_FLIGHT_STATUSES.includes(pair.removal.status);
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

function PreviewList({ preview }: { preview: RemovalPreview }) {
  const lines = [
    plural(preview.transactions, "transaction", "transactions"),
    preview.statementSections > 0 ? plural(preview.statementSections, "account section", "account sections") : null,
    preview.recategorizationJobs > 0 ? plural(preview.recategorizationJobs, "recategorization job", "recategorization jobs") : null,
    preview.recategorizationProposals > 0
      ? plural(preview.recategorizationProposals, "recategorization proposal", "recategorization proposals")
      : null,
    preview.categorizationDisagreements > 0
      ? plural(preview.categorizationDisagreements, "category disagreement", "category disagreements")
      : null,
    preview.recurringPaymentMatches > 0
      ? plural(preview.recurringPaymentMatches, "recurring-payment match", "recurring-payment matches")
      : null,
  ].filter((line): line is string => line !== null);

  return (
    <ul data-testid="removal-preview" className="mt-2 list-disc pl-5 text-sm">
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}

function RemovalConfirmDialog({
  pair,
  onClose,
  onConfirm,
  pending,
  error,
}: {
  pair: DuplicatePair;
  onClose: () => void;
  onConfirm: () => void;
  pending: boolean;
  error: string | null;
}) {
  const preview = pair.preview;
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30" />
        <Dialog.Content
          data-testid="removal-dialog"
          className="fixed left-1/2 top-1/2 max-h-[90vh] w-[min(92vw,32rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded bg-white p-4 shadow-lg dark:bg-slate-800 dark:text-slate-100"
        >
          <Dialog.Title className="font-medium">Permanently remove this duplicate?</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm">
            Remove <strong>{formatStatementLabel(pair.remove)}</strong> and keep{" "}
            <strong>{formatStatementLabel(pair.keep)}</strong>.
          </Dialog.Description>
          {preview && (
            <>
              <p className="mt-3 text-sm">This will permanently delete:</p>
              <PreviewList preview={preview} />
              <p className="mt-2 text-sm">The removed transactions&apos; search embeddings are deleted too.</p>
              {preview.onlyOnRemovedCopy > 0 && (
                <p data-testid="removal-only-on-copy" className="mt-2 text-sm font-medium text-amber-700 dark:text-amber-400">
                  {plural(preview.onlyOnRemovedCopy, "transaction exists", "transactions exist")} only on this copy and
                  will be lost.
                </p>
              )}
              {preview.correctionsLost > 0 && (
                <p data-testid="removal-corrections-lost" className="mt-2 text-sm font-medium text-amber-700 dark:text-amber-400">
                  {plural(preview.correctionsLost, "manual correction", "manual corrections")} on this copy will be lost.
                </p>
              )}
            </>
          )}
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">The file in Google Drive is not touched.</p>
          {error && (
            <p data-testid="removal-dialog-error" className="mt-2 text-sm text-red-600 dark:text-red-400">
              {error}
            </p>
          )}
          <div className="mt-4 flex justify-end gap-3">
            <button onClick={onClose} className="px-2 py-1 text-slate-600 dark:text-slate-300">
              Cancel
            </button>
            <button
              data-testid="confirm-removal"
              onClick={onConfirm}
              disabled={pending || !preview}
              className="rounded bg-red-700 px-3 py-1 text-white disabled:opacity-50 dark:bg-red-600"
            >
              Delete permanently
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function RemovalStatusLine({ pair }: { pair: DuplicatePair }) {
  const removal = pair.removal;
  if (!removal) return null;
  let text: string;
  let tone = "text-slate-600 dark:text-slate-300";
  switch (removal.status) {
    case "queued":
      text = "Removal requested -- waiting for the worker...";
      break;
    case "running":
      text = "Removing...";
      break;
    case "embeddings_pending":
      text = "Removed -- cleaning up search data...";
      break;
    case "completed":
      text = "Removed.";
      break;
    case "embeddings_failed":
      text = "Removed -- cleaning up the search data failed (harmless; only unused data remains).";
      tone = "text-amber-600 dark:text-amber-400";
      break;
    case "failed":
      text = `Removal failed: ${removal.failureReason ?? "unknown reason"}`;
      tone = "text-red-600 dark:text-red-400";
      break;
  }
  return (
    <p data-testid={`duplicate-removal-status-${pair.id}`} className={`mt-2 text-sm ${tone}`}>
      {text}
    </p>
  );
}

function StatementColumn({ role, pair, which }: { role: string; pair: DuplicatePair; which: "keep" | "remove" }) {
  const label = which === "keep" ? pair.keep : pair.remove;
  const corrections = which === "keep" ? pair.correctionsOnKept : pair.correctionsOnRemoved;
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{role}</p>
      <p className="break-words text-sm">{formatStatementLabel(label)}</p>
      <p className="text-xs text-slate-500 dark:text-slate-400">
        {plural(label.transactionCount, "transaction", "transactions")}
        {corrections !== null && `; ${plural(corrections, "manual correction", "manual corrections")}`}
      </p>
    </div>
  );
}

function PairRow({
  pair,
  onRemove,
  onDismiss,
  busy,
  error,
}: {
  pair: DuplicatePair;
  onRemove: () => void;
  onDismiss: () => void;
  busy: boolean;
  error: string | undefined;
}) {
  const inFlight = isInFlight(pair);
  const decidable = pair.status === "pending" && !inFlight;
  return (
    <li data-testid={`duplicate-pair-${pair.id}`} className="mb-3 rounded border border-slate-200 p-3 dark:border-slate-700">
      <div className="grid gap-3 sm:grid-cols-2">
        <StatementColumn role="Keep" pair={pair} which="keep" />
        <StatementColumn role="Remove" pair={pair} which="remove" />
      </div>

      {decidable && pair.stale && (
        <p data-testid={`duplicate-stale-${pair.id}`} className="mt-2 text-sm text-amber-600 dark:text-amber-400">
          One of these statements no longer exists.
        </p>
      )}
      {decidable && !pair.stale && !pair.removalOffered && (
        <p data-testid={`duplicate-info-only-${pair.id}`} className="mt-2 text-sm text-amber-600 dark:text-amber-400">
          These statements differ in size, so this is listed for information only.
        </p>
      )}

      <RemovalStatusLine pair={pair} />

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <Link
          data-testid={`duplicate-view-${pair.id}`}
          to={`/duplicates/${pair.comparisonId}`}
          className="py-1 text-slate-900 underline dark:text-slate-100"
        >
          View comparison
        </Link>
        {decidable && pair.removalOffered && (
          <button
            data-testid={`duplicate-remove-${pair.id}`}
            onClick={onRemove}
            disabled={busy}
            className="py-1 text-red-700 underline disabled:opacity-50 dark:text-red-400"
          >
            Remove duplicate...
          </button>
        )}
        {decidable && (
          <button
            data-testid={`duplicate-dismiss-${pair.id}`}
            onClick={onDismiss}
            disabled={busy}
            className="py-1 text-slate-500 underline disabled:opacity-50 dark:text-slate-400"
          >
            Not a duplicate -- dismiss
          </button>
        )}
      </div>
      {error && (
        <p data-testid={`duplicate-error-${pair.id}`} className="mt-1 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
    </li>
  );
}

function Group({ testId, title, pairs, renderPair }: { testId: string; title: string; pairs: DuplicatePair[]; renderPair: (p: DuplicatePair) => ReactNode }) {
  if (pairs.length === 0) return null;
  return (
    <div data-testid={testId} className="mt-3">
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      <ul>{pairs.map(renderPair)}</ul>
    </div>
  );
}

export function DuplicateStatementsPanel() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [confirming, setConfirming] = useState<DuplicatePair | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [recheckSent, setRecheckSent] = useState(false);

  const { data: pairs } = useQuery({
    queryKey: ["duplicates", "pairs", page],
    queryFn: () => listPairs(page, PAGE_SIZE),
    // Poll only while a removal is in flight: the user asked for it and is waiting to see it finish.
    refetchInterval: (query) => {
      const current = query.state.data as DuplicatePairPage | undefined;
      return current?.items.some(isInFlight) ? IN_FLIGHT_POLL_INTERVAL_MS : false;
    },
  });
  const { data: scan } = useQuery({ queryKey: ["duplicates", "scanStatus"], queryFn: getScanStatus });

  // Pair list, pending count (the nav badge) and scan status are refreshed together, so they never disagree.
  const refreshAll = () => queryClient.invalidateQueries({ queryKey: ["duplicates"] });

  const removalMutation = useMutation({
    mutationFn: (pair: DuplicatePair) =>
      requestRemoval(pair.id, {
        removeStatementHash: pair.remove.contentHash,
        // Exactly the number the confirmation showed, so the server can tell if it changed since.
        acknowledgedCorrectionsLost: pair.preview?.correctionsLost ?? 0,
      }),
    onSuccess: () => {
      setConfirming(null);
      setDialogError(null);
      setNotice(null);
      refreshAll();
    },
    onError: (error) => {
      if (STALE_ACTION_ERRORS.has(errorCode(error) ?? "")) {
        // What the user was looking at is out of date: close the dialog, refresh, say what happened. Nothing was deleted.
        setConfirming(null);
        setDialogError(null);
        setNotice(duplicateErrorMessage(error));
        refreshAll();
      } else {
        setDialogError(duplicateErrorMessage(error));
      }
    },
  });

  const dismissMutation = useMutation({
    mutationFn: (pair: DuplicatePair) => dismissPair(pair.id),
    onSuccess: (_data, pair) => {
      setRowErrors((e) => ({ ...e, [pair.id]: "" }));
      refreshAll();
    },
    onError: (error, pair) => {
      setRowErrors((e) => ({ ...e, [pair.id]: duplicateErrorMessage(error) }));
      if (STALE_ACTION_ERRORS.has(errorCode(error) ?? "")) refreshAll();
    },
  });

  const recheckMutation = useMutation({
    mutationFn: requestRecheck,
    onSuccess: () => {
      setRecheckSent(true);
      refreshAll();
    },
  });

  const items = pairs?.items ?? [];
  const beingRemoved = items.filter(isInFlight);
  const awaiting = items.filter((p) => p.status === "pending" && !isInFlight(p));
  const recentlyRemoved = items.filter((p) => p.status === "removed" && !isInFlight(p));
  const nothingListed = beingRemoved.length + awaiting.length + recentlyRemoved.length === 0;
  const totalCount = pairs?.totalCount ?? 0;
  const hasNextPage = page * PAGE_SIZE < totalCount;
  const busy = dismissMutation.isPending || removalMutation.isPending;

  const renderPair = (pair: DuplicatePair) => (
    <PairRow
      key={pair.id}
      pair={pair}
      busy={busy}
      error={rowErrors[pair.id] || undefined}
      onRemove={() => {
        setDialogError(null);
        setNotice(null);
        setConfirming(pair);
      }}
      onDismiss={() => dismissMutation.mutate(pair)}
    />
  );

  return (
    <div data-testid="duplicates-panel" className="mb-6 rounded border border-slate-200 p-4 dark:border-slate-700">
      <h2 className="mb-1 font-medium">Probable duplicate statements</h2>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500 dark:text-slate-400">
        <span data-testid="duplicates-scan-line">
          {scan?.lastCompletedAt
            ? `Last checked ${new Date(scan.lastCompletedAt).toLocaleString()}${scan.pairsFound !== null ? `; ${scan.pairsFound} found` : ""}.`
            : "Not checked yet."}
        </span>
        <button
          data-testid="duplicates-check-again"
          onClick={() => recheckMutation.mutate()}
          disabled={recheckMutation.isPending}
          className="py-1 underline disabled:opacity-50"
        >
          Check again
        </button>
        {(recheckSent || scan?.recheckRequested) && (
          <span data-testid="duplicates-recheck-requested">Re-check requested; the worker will look shortly.</span>
        )}
      </div>

      {notice && (
        <p data-testid="duplicates-notice" className="mt-2 text-sm text-amber-600 dark:text-amber-400">
          {notice}
        </p>
      )}

      {nothingListed && scan && !scan.detectionEnabled && (
        <p data-testid="duplicates-off" className="mt-3 text-sm text-slate-500 dark:text-slate-400">
          Duplicate detection is switched off.{" "}
          <Link to="/settings" className="underline">
            Change it in Settings
          </Link>
          .
        </p>
      )}
      {nothingListed && scan && scan.detectionEnabled && (
        <p data-testid="duplicates-none" className="mt-3 text-sm text-slate-500 dark:text-slate-400">
          No probable duplicate statements.
        </p>
      )}

      <Group testId="duplicates-group-removing" title="Being removed" pairs={beingRemoved} renderPair={renderPair} />
      <Group testId="duplicates-group-awaiting" title="Awaiting your decision" pairs={awaiting} renderPair={renderPair} />
      <Group testId="duplicates-group-removed" title="Removed in the last 24 hours" pairs={recentlyRemoved} renderPair={renderPair} />

      {totalCount > PAGE_SIZE && (
        <div className="mt-3 flex items-center gap-3 text-sm">
          <button disabled={page === 1} onClick={() => setPage((p) => p - 1)} className="disabled:opacity-50">
            Previous
          </button>
          <span>Page {page}</span>
          <button disabled={!hasNextPage} onClick={() => setPage((p) => p + 1)} className="disabled:opacity-50">
            Next
          </button>
        </div>
      )}

      {confirming && (
        <RemovalConfirmDialog
          pair={confirming}
          onClose={() => setConfirming(null)}
          onConfirm={() => removalMutation.mutate(confirming)}
          pending={removalMutation.isPending}
          error={dialogError}
        />
      )}
    </div>
  );
}
