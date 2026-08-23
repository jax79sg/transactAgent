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
}: {
  label: string;
  sortKey: K;
  activeSortKey: K | undefined;
  sortDir: "asc" | "desc";
  onSort: (key: K, dir: "asc" | "desc") => void;
  className?: string;
  colSpan?: number;
}) {
  const isActive = activeSortKey === sortKey;
  const nextDir = isActive && sortDir === "asc" ? "desc" : "asc";

  return (
    <th className={className} colSpan={colSpan}>
      <button
        type="button"
        data-testid={`sort-${sortKey}`}
        aria-sort={isActive ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
        className="flex items-center gap-1 whitespace-nowrap hover:text-slate-900 dark:hover:text-slate-100"
        onClick={() => onSort(sortKey, nextDir)}
      >
        {label}
        <span className="text-[10px] leading-none" aria-hidden="true">
          {isActive ? (sortDir === "asc" ? "▲" : "▼") : ""}
        </span>
      </button>
    </th>
  );
}
