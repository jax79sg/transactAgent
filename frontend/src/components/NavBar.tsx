import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink } from "react-router-dom";

import { getActivitySummary } from "../api/backgroundActivity";
import { getPendingCount } from "../api/recategorization";
import { getRecurringPaymentsStatus } from "../api/recurringPayments";
import type { BackgroundJobType } from "../api/types";
import { useAuth } from "../context/AuthContext";
import { useTheme, type Theme } from "../context/ThemeContext";

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
      className="ml-1 rounded-full bg-amber-500 px-1.5 py-0.5 text-xs font-semibold text-white dark:bg-amber-600"
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
  // Issue #15: dueSoonCount now included -- the previous exclusion ("nothing's
  // gone wrong yet") meant a due-soon payment was invisible anywhere outside the
  // Dashboard tab, so a user had no way to notice an upcoming payment without
  // remembering to go check manually. Being due soon isn't a problem, but it's
  // exactly the thing this badge exists to surface ahead of time.
  const attentionCount = data.dueSoonCount + data.overdueCount + data.pendingMatchCount + data.newSuggestionCount;
  if (attentionCount === 0) return null;

  return (
    <span
      data-testid="recurring-payments-badge"
      className="ml-1 rounded-full bg-amber-500 px-1.5 py-0.5 text-xs font-semibold text-white dark:bg-amber-600"
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
        className="flex items-center gap-2 rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
      >
        <span
          data-testid="activity-dot"
          className={
            current
              ? "h-2 w-2 animate-pulse rounded-full bg-emerald-500"
              : "h-2 w-2 rounded-full bg-slate-300 dark:bg-slate-600"
          }
        />
        {current && <span>{JOB_TYPE_LABELS[current.jobType]} in progress</span>}
      </button>

      {isOpen && (
        <div
          data-testid="activity-panel"
          className="absolute right-0 z-10 mt-1 w-72 rounded border border-slate-200 bg-white p-3 shadow-lg dark:border-slate-700 dark:bg-slate-800"
        >
          <div className="mb-2 text-xs font-semibold text-slate-500 dark:text-slate-400">Background activity</div>
          {current && (
            <div className="mb-2 text-sm text-emerald-700 dark:text-emerald-400">
              {JOB_TYPE_LABELS[current.jobType]} in progress
            </div>
          )}
          {recent.length === 0 ? (
            <div className="text-sm text-slate-400 dark:text-slate-500">No recent activity</div>
          ) : (
            <ul className="space-y-1">
              {recent.map((entry, index) => (
                <li key={index} className="text-sm text-slate-600 dark:text-slate-300">
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

const THEME_ICON: Record<Theme, string> = { light: "🌙", dark: "☀️" };
const THEME_TOGGLE_LABEL: Record<Theme, string> = { light: "Switch to dark mode", dark: "Switch to light mode" };

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      data-testid="theme-toggle"
      aria-label={THEME_TOGGLE_LABEL[theme]}
      title={THEME_TOGGLE_LABEL[theme]}
      onClick={toggleTheme}
      className="flex items-center gap-1 rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
    >
      <span aria-hidden="true">{THEME_ICON[theme]}</span>
      <span data-testid="theme-toggle-label">{theme === "dark" ? "Dark" : "Light"}</span>
    </button>
  );
}

export function NavBar() {
  const { logout } = useAuth();

  return (
    <nav className="flex items-center justify-between gap-4 overflow-x-auto border-b border-slate-200 px-6 py-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex shrink-0 gap-6">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === "/"}
            className={({ isActive }) =>
              isActive
                ? "font-semibold text-slate-900 dark:text-slate-100"
                : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
            }
          >
            {link.label}
            {link.to === "/review" && <PendingReviewBadge />}
            {link.to === "/" && <RecurringPaymentsBadge />}
          </NavLink>
        ))}
      </div>
      <div className="flex shrink-0 items-center gap-4">
        <ActivityIndicator />
        <ThemeToggle />
        <button
          data-testid="logout-button"
          className="text-sm text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
          onClick={logout}
        >
          Log out
        </button>
      </div>
    </nav>
  );
}
