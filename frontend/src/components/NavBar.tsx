import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink } from "react-router-dom";

import { getActivitySummary } from "../api/backgroundActivity";
import { getPendingCount } from "../api/recategorization";
import { getRecurringPaymentsStatus } from "../api/recurringPayments";
import type { BackgroundJobType } from "../api/types";
import { useAuth } from "../context/AuthContext";

const LINKS = [
  { to: "/", label: "Dashboard" },
  { to: "/transactions", label: "Transactions" },
  { to: "/ask-ai", label: "Ask AI" },
  { to: "/ingestion", label: "Ingestion" },
  { to: "/review", label: "Review" },
  { to: "/settings", label: "Settings" },
];

// 30s, deliberately looser than Ingestion's 3s active-run poll -- this is an ambient
// background indicator nobody is actively watching, not a run the user just
// triggered and is waiting on (business-logic-model.md).
const PENDING_COUNT_POLL_INTERVAL_MS = 30000;

function PendingReviewBadge() {
  const { data } = useQuery({
    queryKey: ["recategorization", "pendingCount"],
    queryFn: getPendingCount,
    refetchInterval: PENDING_COUNT_POLL_INTERVAL_MS,
  });

  if (!data || data.pendingCount === 0) return null;

  return (
    <span
      data-testid="pending-review-badge"
      className="ml-1 rounded-full bg-amber-500 px-1.5 py-0.5 text-xs font-semibold text-white"
    >
      {data.pendingCount}
    </span>
  );
}

// 5min, matching BackupStatusPanel's cadence (business-logic-model.md) -- a
// recurring-payment status changes at most daily, so this is even less
// time-sensitive than the 30s pending-review badge.
const RECURRING_PAYMENTS_STATUS_POLL_INTERVAL_MS = 5 * 60 * 1000;

function RecurringPaymentsBadge() {
  const { data } = useQuery({
    queryKey: ["recurringPayments", "status"],
    queryFn: getRecurringPaymentsStatus,
    refetchInterval: RECURRING_PAYMENTS_STATUS_POLL_INTERVAL_MS,
  });

  if (!data) return null;
  // dueSoonCount deliberately excluded -- nothing has gone wrong yet for a
  // due-soon item (business-logic-model.md).
  const attentionCount = data.overdueCount + data.pendingMatchCount + data.newSuggestionCount;
  if (attentionCount === 0) return null;

  return (
    <span
      data-testid="recurring-payments-badge"
      className="ml-1 rounded-full bg-amber-500 px-1.5 py-0.5 text-xs font-semibold text-white"
    >
      {attentionCount}
    </span>
  );
}

// 3s, matching the Ingestion page's own active-run polling cadence (NFR-BPV-1) --
// far tighter than the 30s/5min cadences of the two count badges above, since this
// represents "something is happening right now", not a backlog.
const ACTIVITY_POLL_INTERVAL_MS = 3000;

const JOB_TYPE_LABELS: Record<BackgroundJobType, string> = {
  ingestion_run: "Ingestion run",
  recategorization_job: "Recategorization scan",
};

function ActivityIndicator() {
  const [isOpen, setIsOpen] = useState(false);
  const { data } = useQuery({
    queryKey: ["backgroundActivity", "summary"],
    queryFn: getActivitySummary,
    refetchInterval: ACTIVITY_POLL_INTERVAL_MS,
  });

  const current = data?.current ?? null;
  const recent = data?.recent ?? [];

  return (
    <div className="relative">
      <button
        type="button"
        data-testid="activity-indicator"
        aria-label={current ? `${JOB_TYPE_LABELS[current.jobType]} in progress` : "Background activity"}
        onClick={() => setIsOpen((open) => !open)}
        className="flex items-center gap-2 rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100"
      >
        <span
          data-testid="activity-dot"
          className={
            current
              ? "h-2 w-2 animate-pulse rounded-full bg-emerald-500"
              : "h-2 w-2 rounded-full bg-slate-300"
          }
        />
        {current && <span>{JOB_TYPE_LABELS[current.jobType]} in progress</span>}
      </button>

      {isOpen && (
        <div
          data-testid="activity-panel"
          className="absolute right-0 z-10 mt-1 w-72 rounded border border-slate-200 bg-white p-3 shadow-lg"
        >
          <div className="mb-2 text-xs font-semibold text-slate-500">Background activity</div>
          {current && (
            <div className="mb-2 text-sm text-emerald-700">{JOB_TYPE_LABELS[current.jobType]} in progress</div>
          )}
          {recent.length === 0 ? (
            <div className="text-sm text-slate-400">No recent activity</div>
          ) : (
            <ul className="space-y-1">
              {recent.map((entry, index) => (
                <li key={index} className="text-sm text-slate-600">
                  {JOB_TYPE_LABELS[entry.jobType]} completed {new Date(entry.completedAt).toLocaleString()}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function NavBar() {
  const { logout } = useAuth();

  return (
    <nav className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
      <div className="flex gap-6">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === "/"}
            className={({ isActive }) =>
              isActive ? "font-semibold text-slate-900" : "text-slate-500 hover:text-slate-800"
            }
          >
            {link.label}
            {link.to === "/review" && <PendingReviewBadge />}
            {link.to === "/" && <RecurringPaymentsBadge />}
          </NavLink>
        ))}
      </div>
      <div className="flex items-center gap-4">
        <ActivityIndicator />
        <button data-testid="logout-button" className="text-sm text-slate-500 hover:text-slate-800" onClick={logout}>
          Log out
        </button>
      </div>
    </nav>
  );
}
