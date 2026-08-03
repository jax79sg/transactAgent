import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";

import { getPendingCount } from "../api/recategorization";
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
          </NavLink>
        ))}
      </div>
      <button data-testid="logout-button" className="text-sm text-slate-500 hover:text-slate-800" onClick={logout}>
        Log out
      </button>
    </nav>
  );
}
