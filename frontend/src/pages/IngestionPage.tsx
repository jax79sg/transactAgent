import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { cancelRun, getRunStatus, listRunFiles, listRunHistory, listRunLogs, startRun } from "../api/ingestion";
import type { IngestionRunStatus, RunFileDetail, RunLogLine, RunStatusResponse } from "../api/types";
import { SortableTh } from "../components/SortableTh";

const ACTIVE_STATUSES: IngestionRunStatus[] = ["queued", "running"];
const POLL_INTERVAL_MS = 3000; // business-logic-model.md: 3s poll while a run is active
const LOG_POLL_INTERVAL_MS = 2000;

export function RunLiveLogs({ runId, isActive }: { runId: string; isActive: boolean }) {
  const [lines, setLines] = useState<RunLogLine[]>([]);
  const lastIdRef = useRef<number | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);

  // Reset accumulated state when switching which run's logs are shown -- otherwise a
  // previous run's tail would linger under a newly-expanded row.
  useEffect(() => {
    setLines([]);
    lastIdRef.current = undefined;
  }, [runId]);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const newLines = await listRunLogs(runId, lastIdRef.current);
        if (cancelled || newLines.length === 0) return;
        lastIdRef.current = newLines[newLines.length - 1].id;
        setLines((prev) => [...prev, ...newLines]);
      } catch {
        // A single missed poll isn't worth surfacing to the user -- the next tick (or
        // the final poll once the run stops being active) will pick up where it left off.
      }
    };

    void poll();
    if (!isActive) return;

    const interval = setInterval(poll, LOG_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [runId, isActive]);

  // Auto-scroll to the newest line, but only if the user was already at (or near) the
  // bottom -- otherwise scrolling back to read earlier lines would keep getting yanked
  // down by new output.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom < 40) el.scrollTop = el.scrollHeight;
  }, [lines]);

  if (lines.length === 0) {
    return <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">No log output yet.</p>;
  }

  return (
    <div
      ref={containerRef}
      data-testid="run-live-logs"
      className="mt-2 max-h-64 overflow-y-auto rounded bg-slate-950 p-2 font-mono text-xs text-slate-100"
    >
      {lines.map((line) => (
        <div key={line.id} className={line.level === "ERROR" || line.level === "WARNING" ? "text-amber-300" : ""}>
          <span className="text-slate-500">{new Date(line.loggedAt).toLocaleTimeString()}</span>{" "}
          <span className="text-slate-400">{line.loggerName}</span> {line.message}
        </div>
      ))}
    </div>
  );
}

type RunFileSortKey = "driveFileName" | "outcome" | "failureReason" | "transactionsExtractedCount";

function sortRunFiles(files: RunFileDetail[], sortKey: RunFileSortKey, sortDir: "asc" | "desc"): RunFileDetail[] {
  const sorted = [...files].sort((a, b) => {
    switch (sortKey) {
      case "driveFileName":
        return a.driveFileName.localeCompare(b.driveFileName);
      case "outcome":
        return a.outcome.localeCompare(b.outcome);
      case "failureReason":
        return (a.failureReason ?? "").localeCompare(b.failureReason ?? "");
      case "transactionsExtractedCount":
        return (a.transactionsExtractedCount ?? 0) - (b.transactionsExtractedCount ?? 0);
    }
  });
  return sortDir === "asc" ? sorted : sorted.reverse();
}

function RunFiles({ runId }: { runId: string }) {
  const [sortKey, setSortKey] = useState<RunFileSortKey>("driveFileName");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const handleSort = (key: RunFileSortKey, dir: "asc" | "desc") => {
    setSortKey(key);
    setSortDir(dir);
  };

  const { data: files, isPending } = useQuery({
    queryKey: ["ingestion", "runFiles", runId],
    queryFn: () => listRunFiles(runId),
  });

  if (isPending) return <p className="text-sm text-slate-500 dark:text-slate-400">Loading files...</p>;

  return (
    <table className="mt-2 w-full text-xs">
      <thead>
        <tr className="text-left text-slate-500 dark:text-slate-400">
          <SortableTh label="File" sortKey="driveFileName" activeSortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
          <SortableTh label="Outcome" sortKey="outcome" activeSortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
          <SortableTh
            label="Reason"
            sortKey="failureReason"
            activeSortKey={sortKey}
            sortDir={sortDir}
            onSort={handleSort}
          />
          <SortableTh
            label="Transactions"
            sortKey="transactionsExtractedCount"
            activeSortKey={sortKey}
            sortDir={sortDir}
            onSort={handleSort}
          />
        </tr>
      </thead>
      <tbody>
        {files && sortRunFiles(files, sortKey, sortDir).map((f) => (
          <tr key={f.id}>
            <td>{f.driveFileName}</td>
            <td>{f.outcome}</td>
            <td>{f.failureReason ?? ""}</td>
            <td>{f.transactionsExtractedCount ?? ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

type RunHistorySortKey =
  | "startedAt"
  | "status"
  | "filesFoundCount"
  | "filesProcessedCount"
  | "filesSkippedCount"
  | "filesFailedCount";

function sortRunHistory(
  runs: RunStatusResponse[],
  sortKey: RunHistorySortKey,
  sortDir: "asc" | "desc",
): RunStatusResponse[] {
  const sorted = [...runs].sort((a, b) => {
    switch (sortKey) {
      case "startedAt":
        return a.startedAt.localeCompare(b.startedAt);
      case "status":
        return a.status.localeCompare(b.status);
      default:
        return a[sortKey] - b[sortKey];
    }
  });
  return sortDir === "asc" ? sorted : sorted.reverse();
}

export function IngestionPage() {
  const queryClient = useQueryClient();
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [historySortKey, setHistorySortKey] = useState<RunHistorySortKey>("startedAt");
  const [historySortDir, setHistorySortDir] = useState<"asc" | "desc">("desc");
  const handleHistorySort = (key: RunHistorySortKey, dir: "asc" | "desc") => {
    setHistorySortKey(key);
    setHistorySortDir(dir);
  };

  const { data: history } = useQuery({
    queryKey: ["ingestion", "history"],
    queryFn: () => listRunHistory(1),
  });

  // Recover an in-progress run after a page reload/navigation, per
  // business-logic-model.md, rather than relying on in-memory state alone.
  const mostRecentRun = history?.items[0];
  const inferredActiveRunId =
    activeRunId ?? (mostRecentRun && ACTIVE_STATUSES.includes(mostRecentRun.status) ? mostRecentRun.runId : null);

  const { data: activeRun } = useQuery({
    queryKey: ["ingestion", "run", inferredActiveRunId],
    queryFn: () => getRunStatus(inferredActiveRunId as string),
    enabled: inferredActiveRunId !== null,
    refetchInterval: (query) =>
      query.state.data && ACTIVE_STATUSES.includes(query.state.data.status) ? POLL_INTERVAL_MS : false,
  });

  const isRunActive = activeRun ? ACTIVE_STATUSES.includes(activeRun.status) : inferredActiveRunId !== null;

  const triggerMutation = useMutation({
    mutationFn: startRun,
    onSuccess: ({ runId }) => {
      setActiveRunId(runId);
      queryClient.invalidateQueries({ queryKey: ["ingestion", "history"] });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: cancelRun,
    onSuccess: (updatedRun) => {
      queryClient.setQueryData(["ingestion", "run", updatedRun.runId], updatedRun);
    },
  });

  // A cancel request takes effect between files, not instantly -- while it's
  // active (status still queued/running) show a distinct "Cancelling..." state
  // rather than letting it look identical to a normal active run.
  const isCancelling = activeRun?.cancelRequestedAt != null && isRunActive;

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Ingestion</h1>

      <button
        data-testid="trigger-run-button"
        disabled={isRunActive || triggerMutation.isPending}
        onClick={() => triggerMutation.mutate()}
        className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
      >
        {isRunActive ? "Run in progress..." : "Run Ingestion"}
      </button>

      {activeRun && (
        <div className="mt-4 rounded border border-slate-200 p-4 text-sm dark:border-slate-700">
          <div className="flex items-center justify-between">
            <p className="font-medium">
              Run status: {isCancelling ? "Cancelling... (stops after the current file)" : activeRun.status}
            </p>
            {isRunActive && (
              <button
                data-testid="cancel-run-button"
                disabled={isCancelling || cancelMutation.isPending}
                onClick={() => cancelMutation.mutate(activeRun.runId)}
                className="rounded border border-slate-300 px-3 py-1 text-xs disabled:opacity-50 dark:border-slate-600 dark:text-slate-300"
              >
                {isCancelling ? "Cancelling..." : "Cancel"}
              </button>
            )}
          </div>
          <p>
            Found {activeRun.filesFoundCount} / Processed {activeRun.filesProcessedCount} / Skipped{" "}
            {activeRun.filesSkippedCount} / Failed {activeRun.filesFailedCount}
          </p>
          <RunLiveLogs runId={activeRun.runId} isActive={isRunActive} />
        </div>
      )}

      <h2 className="mb-2 mt-8 text-lg font-medium">Run History</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-500 dark:text-slate-400">
            <SortableTh
              label="Started"
              sortKey="startedAt"
              activeSortKey={historySortKey}
              sortDir={historySortDir}
              onSort={handleHistorySort}
            />
            <SortableTh
              label="Status"
              sortKey="status"
              activeSortKey={historySortKey}
              sortDir={historySortDir}
              onSort={handleHistorySort}
            />
            <SortableTh
              label="Found"
              sortKey="filesFoundCount"
              activeSortKey={historySortKey}
              sortDir={historySortDir}
              onSort={handleHistorySort}
            />
            <SortableTh
              label="Processed"
              sortKey="filesProcessedCount"
              activeSortKey={historySortKey}
              sortDir={historySortDir}
              onSort={handleHistorySort}
            />
            <SortableTh
              label="Skipped"
              sortKey="filesSkippedCount"
              activeSortKey={historySortKey}
              sortDir={historySortDir}
              onSort={handleHistorySort}
            />
            <SortableTh
              label="Failed"
              sortKey="filesFailedCount"
              activeSortKey={historySortKey}
              sortDir={historySortDir}
              onSort={handleHistorySort}
            />
          </tr>
        </thead>
        <tbody>
          {history && sortRunHistory(history.items, historySortKey, historySortDir).map((run) => (
            <>
              <tr
                key={run.runId}
                data-testid={`run-history-row-${run.runId}`}
                className="cursor-pointer border-b border-slate-100 dark:border-slate-800"
                onClick={() => setExpandedRunId(expandedRunId === run.runId ? null : run.runId)}
              >
                <td>{run.startedAt}</td>
                <td>{run.status}</td>
                <td>{run.filesFoundCount}</td>
                <td>{run.filesProcessedCount}</td>
                <td>{run.filesSkippedCount}</td>
                <td>{run.filesFailedCount}</td>
              </tr>
              {expandedRunId === run.runId && (
                <tr>
                  <td colSpan={6}>
                    <RunFiles runId={run.runId} />
                    <RunLiveLogs
                      runId={run.runId}
                      isActive={run.runId === activeRun?.runId ? isRunActive : ACTIVE_STATUSES.includes(run.status)}
                    />
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}
