import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { getBackupStatus } from "../api/backup";
import {
  approveProposal,
  bulkApproveProposals,
  bulkRejectProposals,
  listPendingDisagreements,
  listPendingProposals,
  type ProposalSortByOption,
  rejectDisagreement,
  rejectProposal,
  resolveDisagreement,
} from "../api/recategorization";
import type { DisagreementDTO } from "../api/types";
import { SortableTh } from "../components/SortableTh";

const PAGE_SIZE = 20;

// A backup outcome changes at most once a night (WR-11/BR-17), so this is looser
// than PendingReviewBadge's 30s -- see business-logic-model.md.
const BACKUP_STATUS_POLL_INTERVAL_MS = 5 * 60 * 1000;

function BackupStatusPanel() {
  const { data } = useQuery({
    queryKey: ["backups", "status"],
    queryFn: getBackupStatus,
    refetchInterval: BACKUP_STATUS_POLL_INTERVAL_MS,
  });

  let content: ReactNode;
  if (!data || data.outcome === null) {
    content = (
      <p data-testid="backup-status-none" className="text-sm text-slate-500 dark:text-slate-400">
        No backups yet.
      </p>
    );
  } else if (data.outcome === "success") {
    content = (
      <p data-testid="backup-status-success" className="text-sm text-slate-600 dark:text-slate-300">
        Last backup succeeded at {new Date(data.lastRunAt as string).toLocaleString()}
        {data.transactionCount !== null && ` (${data.transactionCount} transactions)`}.
      </p>
    );
  } else if (data.failureCategory === "drive_connectivity") {
    content = (
      <p data-testid="backup-status-failed-drive" className="text-sm text-amber-600 dark:text-amber-400">
        Backup failed -- Google Drive isn't connected.{" "}
        <Link to="/settings" className="underline">
          Reconnect Google Drive
        </Link>
        .
      </p>
    );
  } else {
    content = (
      <p data-testid="backup-status-failed-other" className="text-sm text-amber-600 dark:text-amber-400">
        Last backup failed.
      </p>
    );
  }

  return (
    <div data-testid="backup-status-panel" className="mb-6 rounded border border-slate-200 p-4 dark:border-slate-700">
      <h2 className="mb-2 font-medium">Backup Status</h2>
      {content}
    </div>
  );
}

// Matching Precision Refinement: a second, separate table -- a genuinely
// different row shape (two candidate categories, no bulk actions, Application
// Design Decision 2) from ProposalTable above, same "visually separate section"
// convention BackupStatusPanel established.
type DisagreementSortKey = "date" | "description" | "amount" | "similarityScore";

function sortDisagreements(
  items: DisagreementDTO[],
  sortKey: DisagreementSortKey,
  sortDir: "asc" | "desc",
): DisagreementDTO[] {
  const sorted = [...items].sort((a, b) => {
    switch (sortKey) {
      case "date":
        return a.candidateTransaction.transactionDate.localeCompare(b.candidateTransaction.transactionDate);
      case "description":
        return a.candidateTransaction.description.localeCompare(b.candidateTransaction.description);
      case "amount": {
        const amountA = Number(a.candidateTransaction.outFlow ?? a.candidateTransaction.inFlow ?? 0);
        const amountB = Number(b.candidateTransaction.outFlow ?? b.candidateTransaction.inFlow ?? 0);
        return amountA - amountB;
      }
      case "similarityScore":
        return Number(a.similarityScore) - Number(b.similarityScore);
    }
  });
  return sortDir === "asc" ? sorted : sorted.reverse();
}

function DisagreementTable() {
  const queryClient = useQueryClient();
  const [singleActionError, setSingleActionError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<DisagreementSortKey>("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const handleSort = (key: DisagreementSortKey, dir: "asc" | "desc") => {
    setSortKey(key);
    setSortDir(dir);
  };

  const { data, isPending } = useQuery({
    queryKey: ["recategorization", "disagreements"],
    queryFn: () => listPendingDisagreements(1, PAGE_SIZE),
  });

  const items = sortDisagreements(data?.items ?? [], sortKey, sortDir);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["recategorization", "disagreements"] });
    queryClient.invalidateQueries({ queryKey: ["recategorization", "pendingCount"] });
  };

  const resolveMutation = useMutation({
    mutationFn: ({ disagreementId, chosenCategoryId }: { disagreementId: string; chosenCategoryId: string }) =>
      resolveDisagreement(disagreementId, chosenCategoryId),
    onSuccess: () => {
      setSingleActionError(null);
      invalidate();
    },
    onError: () => setSingleActionError("Couldn't resolve that disagreement -- it may have already been resolved."),
  });

  const rejectMutation = useMutation({
    mutationFn: rejectDisagreement,
    onSuccess: () => {
      setSingleActionError(null);
      invalidate();
    },
    onError: () => setSingleActionError("Couldn't reject that disagreement -- it may have already been resolved."),
  });

  // Same convention as BackupStatusPanel/empty-state handling elsewhere on this
  // page: a section with nothing to show simply doesn't render, rather than
  // showing its own "nothing here" message alongside ProposalTable's.
  if (isPending || items.length === 0) return null;

  return (
    <div className="mb-6" data-testid="disagreement-section">
      <h2 className="mb-2 font-medium">Category Disagreements</h2>
      <p className="mb-2 text-sm text-slate-500 dark:text-slate-400">
        Similarity matching and the LLM classifier suggested different categories for these transactions -- pick
        one.
      </p>

      {singleActionError && (
        <p data-testid="disagreement-single-action-error" className="mb-3 text-sm text-amber-600 dark:text-amber-400">
          {singleActionError}
        </p>
      )}

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-500 dark:text-slate-400">
            <SortableTh label="Date" sortKey="date" activeSortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
            <SortableTh
              label="Description"
              sortKey="description"
              activeSortKey={sortKey}
              sortDir={sortDir}
              onSort={handleSort}
            />
            <SortableTh label="Amount" sortKey="amount" activeSortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
            <SortableTh
              label="Similarity score"
              sortKey="similarityScore"
              activeSortKey={sortKey}
              sortDir={sortDir}
              onSort={handleSort}
            />
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((disagreement, index) => (
            <tr
              key={disagreement.id}
              data-testid={`disagreement-row-${disagreement.id}`}
              className={`border-b border-slate-100 dark:border-slate-800 ${
                index % 2 === 1 ? "bg-slate-100 dark:bg-slate-800" : "bg-white dark:bg-slate-900"
              }`}
            >
              <td>{disagreement.candidateTransaction.transactionDate}</td>
              <td>{disagreement.candidateTransaction.description}</td>
              <td>{disagreement.candidateTransaction.outFlow ?? disagreement.candidateTransaction.inFlow ?? ""}</td>
              <td>{disagreement.similarityScore}</td>
              <td>
                <button
                  data-testid={`disagreement-use-similarity-${disagreement.id}`}
                  onClick={() =>
                    resolveMutation.mutate({
                      disagreementId: disagreement.id,
                      chosenCategoryId: disagreement.similarityCategory.id,
                    })
                  }
                  className="mr-2 text-slate-900 underline dark:text-slate-100"
                >
                  Use {disagreement.similarityCategory.name}
                </button>
                <button
                  data-testid={`disagreement-use-llm-${disagreement.id}`}
                  onClick={() =>
                    resolveMutation.mutate({
                      disagreementId: disagreement.id,
                      chosenCategoryId: disagreement.llmCategory.id,
                    })
                  }
                  className="mr-2 text-slate-900 underline dark:text-slate-100"
                >
                  Use {disagreement.llmCategory.name}
                </button>
                <button
                  data-testid={`disagreement-reject-${disagreement.id}`}
                  onClick={() => rejectMutation.mutate(disagreement.id)}
                  className="text-slate-500 underline dark:text-slate-400"
                >
                  Reject
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ReviewPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<ProposalSortByOption>("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [failedIds, setFailedIds] = useState<Set<string>>(new Set());
  const [singleActionError, setSingleActionError] = useState<string | null>(null);

  const handleSort = (key: ProposalSortByOption, dir: "asc" | "desc") => {
    setSortBy(key);
    setSortDir(dir);
    setPage(1); // a new sort order invalidates whatever page you were on
  };

  const { data, isPending } = useQuery({
    queryKey: ["recategorization", "proposals", page, sortBy, sortDir],
    queryFn: () => listPendingProposals(page, PAGE_SIZE, sortBy, sortDir),
  });

  const items = data?.items ?? [];

  // Selection state is scoped to the current page/list only, never carried across a
  // page change or after a bulk action removes resolved rows (business-logic-model.md).
  useEffect(() => {
    setSelected(new Set());
  }, [page, data]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["recategorization", "proposals"] });
    queryClient.invalidateQueries({ queryKey: ["recategorization", "pendingCount"] });
  };

  const removeFromSelection = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const approveMutation = useMutation({
    mutationFn: approveProposal,
    onSuccess: (_, proposalId) => {
      removeFromSelection(proposalId);
      setSingleActionError(null);
      invalidate();
    },
    onError: () => setSingleActionError("Couldn't approve that proposal -- it may have already been resolved."),
  });

  const rejectMutation = useMutation({
    mutationFn: rejectProposal,
    onSuccess: (_, proposalId) => {
      removeFromSelection(proposalId);
      setSingleActionError(null);
      invalidate();
    },
    onError: () => setSingleActionError("Couldn't reject that proposal -- it may have already been resolved."),
  });

  const bulkApproveMutation = useMutation({
    mutationFn: bulkApproveProposals,
    onSuccess: (result) => {
      setSelected(new Set());
      setFailedIds(new Set(result.failedIds));
      invalidate();
    },
  });

  const bulkRejectMutation = useMutation({
    mutationFn: bulkRejectProposals,
    onSuccess: (result) => {
      setSelected(new Set());
      setFailedIds(new Set(result.failedIds));
      invalidate();
    },
  });

  const toggleRow = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allSelected = items.length > 0 && selected.size === items.length;
  const toggleSelectAll = () => {
    setSelected(allSelected ? new Set() : new Set(items.map((p) => p.id)));
  };

  const totalCount = data?.totalCount ?? 0;
  const hasNextPage = page * PAGE_SIZE < totalCount;

  if (isPending) return <p className="text-sm text-slate-500 dark:text-slate-400">Loading...</p>;

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Review</h1>

      <BackupStatusPanel />

      <DisagreementTable />

      {singleActionError && (
        <p data-testid="review-single-action-error" className="mb-3 text-sm text-amber-600 dark:text-amber-400">
          {singleActionError}
        </p>
      )}

      {items.length === 0 ? (
        <p data-testid="review-empty-state" className="text-sm text-slate-500 dark:text-slate-400">
          No proposals waiting for review.
        </p>
      ) : (
        <>
          <div className="mb-2 flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                data-testid="review-select-all"
                checked={allSelected}
                onChange={toggleSelectAll}
              />
              Select all
            </label>
            <button
              data-testid="review-bulk-approve"
              disabled={selected.size === 0 || bulkApproveMutation.isPending}
              onClick={() => bulkApproveMutation.mutate(Array.from(selected))}
              className="rounded bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
            >
              Approve selected
            </button>
            <button
              data-testid="review-bulk-reject"
              disabled={selected.size === 0 || bulkRejectMutation.isPending}
              onClick={() => bulkRejectMutation.mutate(Array.from(selected))}
              className="rounded border border-slate-300 px-3 py-1 text-sm disabled:opacity-50 dark:border-slate-600 dark:text-slate-300"
            >
              Reject selected
            </button>
          </div>

          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 dark:text-slate-400">
                <th></th>
                <SortableTh label="Date" sortKey="date" activeSortKey={sortBy} sortDir={sortDir} onSort={handleSort} />
                <th>Description</th>
                <SortableTh label="Amount" sortKey="amount" activeSortKey={sortBy} sortDir={sortDir} onSort={handleSort} />
                <th>Current category</th>
                <th>Proposed category</th>
                <SortableTh label="Score" sortKey="score" activeSortKey={sortBy} sortDir={sortDir} onSort={handleSort} />
                <SortableTh label="Source" sortKey="source" activeSortKey={sortBy} sortDir={sortDir} onSort={handleSort} />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((proposal, index) => (
                <tr
                  key={proposal.id}
                  data-testid={`review-row-${proposal.id}`}
                  className={`border-b border-slate-100 dark:border-slate-800 ${
                    index % 2 === 1 ? "bg-slate-100 dark:bg-slate-800" : "bg-white dark:bg-slate-900"
                  }`}
                >
                  <td>
                    <input
                      type="checkbox"
                      data-testid={`review-row-checkbox-${proposal.id}`}
                      checked={selected.has(proposal.id)}
                      onChange={() => toggleRow(proposal.id)}
                    />
                  </td>
                  <td>{proposal.candidateTransaction.transactionDate}</td>
                  <td>{proposal.candidateTransaction.description}</td>
                  <td>{proposal.candidateTransaction.outFlow ?? proposal.candidateTransaction.inFlow ?? ""}</td>
                  <td>{proposal.candidateTransaction.category.name}</td>
                  <td>{proposal.proposedCategory.name}</td>
                  <td>{proposal.matchScore}</td>
                  <td>{proposal.sourceBucket === "categorized" ? "Already categorized" : "Unsure"}</td>
                  <td>
                    <button
                      data-testid={`review-approve-${proposal.id}`}
                      onClick={() => approveMutation.mutate(proposal.id)}
                      className="mr-2 text-slate-900 underline dark:text-slate-100"
                    >
                      Approve
                    </button>
                    <button
                      data-testid={`review-reject-${proposal.id}`}
                      onClick={() => rejectMutation.mutate(proposal.id)}
                      className="text-slate-500 underline dark:text-slate-400"
                    >
                      Reject
                    </button>
                    {failedIds.has(proposal.id) && (
                      <p
                        data-testid={`review-failed-${proposal.id}`}
                        className="text-xs text-amber-600 dark:text-amber-400"
                      >
                        Couldn't process -- it may have already been resolved.
                      </p>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="mt-3 flex items-center gap-3 text-sm">
            <button
              data-testid="review-prev-page"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
              className="disabled:opacity-50"
            >
              Previous
            </button>
            <span>Page {page}</span>
            <button
              data-testid="review-next-page"
              disabled={!hasNextPage}
              onClick={() => setPage((p) => p + 1)}
              className="disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
