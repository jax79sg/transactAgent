/** Shared clickable `<th>` for every sortable table in the app (issue #10). Click
 * toggles asc/desc when this column is already the active sort key, or switches to
 * this column ascending-first when it isn't -- one convention everywhere rather than
 * each page inventing its own. Purely presentational: the caller owns where sort
 * state actually lives (a page's local useState for a small client-side list, or the
 * URL-backed filter state for a server-paginated one like TransactionsPage).
 */
export function SortableTh<K extends string>({
  label,
  sortKey,
  activeSortKey,
  sortDir,
  onSort,
  className,
  colSpan,
  testId,
}: {
  label: string;
  sortKey: K;
  activeSortKey: K | undefined;
  sortDir: "asc" | "desc";
  onSort: (key: K, dir: "asc" | "desc") => void;
  className?: string;
  colSpan?: number;
  /** Override when two headers share one sortKey (e.g. separate "Out-flow" /
   * "In-flow" columns both sorting by the same combined "amount" key) -- avoids
   * two elements with the same default `sort-${sortKey}` testid. */
  testId?: string;
}) {
  const isActive = activeSortKey === sortKey;
  const nextDir = isActive && sortDir === "asc" ? "desc" : "asc";

  return (
    <th className={className} colSpan={colSpan}>
      <button
        type="button"
        data-testid={testId ?? `sort-${sortKey}`}
        aria-sort={isActive ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
        className="flex cursor-pointer select-none items-center gap-1 whitespace-nowrap hover:text-slate-900 dark:hover:text-slate-100"
        onClick={() => onSort(sortKey, nextDir)}
      >
        {label}
        {/* Always visible, not just on hover/active -- a column that only reveals
            it's sortable when you happen to hover it is a column nobody discovers
            it's sortable at all (found live: issue #10 shipped but nobody could
            tell the feature existed). Dimmed neutral glyph when inactive, solid
            direction arrow once this column is the active sort. */}
        <span className={`text-[10px] leading-none ${isActive ? "" : "text-slate-300 dark:text-slate-600"}`} aria-hidden="true">
          {isActive ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
        </span>
      </button>
    </th>
  );
}
