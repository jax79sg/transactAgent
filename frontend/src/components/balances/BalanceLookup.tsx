import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import { getBalances } from "../../api/balances";
import { balanceErrorMessage, dayBefore, describeLookup, localToday, monthName, monthOf } from "../../lib/balances";
import { BalancesTable } from "./BalancesTable";
import { IngestedThrough, UnlinkedNotice } from "./IngestedThrough";
import { lookupKey } from "./queries";

type Lookup = { mode: "date"; date: string } | { mode: "month"; month: string };

const EARLIEST_DATE = "2000-01-01";
const EARLIEST_YEAR = 2000;
const pad = (n: number): string => String(n).padStart(2, "0");
const CONTROL = "rounded border border-slate-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";
const SEGMENT = "min-h-[36px] px-3 py-1 text-sm";

// Epic 13 (US-13.4, FR-AB-10): look up balances for an exact date or a month. The result, its heading and every limit
// come from the API's answer, never the browser's clock, with one exception: the very first question needs a date, so
// it uses the browser's local calendar date, and if the API says that is in the future (the browser is ahead of the
// reporting time zone) it asks once more for the day before, quietly. After the first answer, `today` is the API's.
export function BalanceLookup({
  onSetBalance,
  onToday,
}: {
  onSetBalance: (accountId: string) => void;
  /** The API's "today", reported whenever an answer arrives, for the dialogs' default and latest date. */
  onToday?: (today: string) => void;
}) {
  const [lookup, setLookup] = useState<Lookup>(() => ({ mode: "date", date: localToday() }));
  const [automatic, setAutomatic] = useState(true);
  const [retried, setRetried] = useState(false);

  const params = lookup.mode === "date" ? { date: lookup.date } : { month: lookup.month };
  const query = useQuery({
    queryKey: lookupKey(params),
    queryFn: () => getBalances(params),
    placeholderData: keepPreviousData,
    retry: false,
  });
  const data = query.data;

  const futureRefusal = query.isError && query.error instanceof ApiError && query.error.body.error === "date_in_future";
  useEffect(() => {
    if (futureRefusal && automatic && !retried && lookup.mode === "date") {
      setRetried(true);
      setLookup({ mode: "date", date: dayBefore(lookup.date) });
    }
  }, [futureRefusal, automatic, retried, lookup]);
  const hideError = futureRefusal && automatic && !retried;

  useEffect(() => {
    if (data) onToday?.(data.today);
  }, [data, onToday]);

  const serverToday = data?.today ?? localToday();
  const [todayYear, todayMonth] = serverToday.split("-").map(Number);

  function change(next: Lookup) {
    setAutomatic(false);
    setLookup(next);
  }

  function switchMode(mode: Lookup["mode"]) {
    if (mode === lookup.mode) return;
    if (mode === "month") {
      change({ mode: "month", month: monthOf(data?.resolvedDate ?? (lookup.mode === "date" ? lookup.date : serverToday)) });
    } else {
      change({ mode: "date", date: data?.resolvedDate ?? serverToday });
    }
  }

  const [monthYear, monthNumber] = lookup.mode === "month" ? lookup.month.split("-").map(Number) : [todayYear, todayMonth];
  const years = Array.from({ length: todayYear - EARLIEST_YEAR + 1 }, (_, i) => todayYear - i);

  return (
    <section data-testid="balance-lookup" className="mb-6">
      <div className="mb-3 flex flex-wrap items-end gap-3 text-sm">
        <div role="group" aria-label="Look up by" className="inline-flex overflow-hidden rounded border border-slate-300 dark:border-slate-600">
          <button
            type="button"
            data-testid="lookup-mode-date"
            aria-pressed={lookup.mode === "date"}
            onClick={() => switchMode("date")}
            className={`${SEGMENT} ${lookup.mode === "date" ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : ""}`}
          >
            Date
          </button>
          <button
            type="button"
            data-testid="lookup-mode-month"
            aria-pressed={lookup.mode === "month"}
            onClick={() => switchMode("month")}
            className={`${SEGMENT} ${lookup.mode === "month" ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : ""}`}
          >
            Month
          </button>
        </div>

        {lookup.mode === "date" ? (
          <>
            <label className="flex items-center gap-2">
              <span className="sr-only">Date</span>
              <input
                type="date"
                data-testid="lookup-date-input"
                min={EARLIEST_DATE}
                max={serverToday}
                value={lookup.date}
                onChange={(event) => {
                  const value = event.target.value;
                  if (value && value >= EARLIEST_DATE && value <= serverToday) change({ mode: "date", date: value });
                }}
                className={CONTROL}
              />
            </label>
            <button
              type="button"
              data-testid="lookup-today-button"
              onClick={() => change({ mode: "date", date: serverToday })}
              className="min-h-[36px] rounded border border-slate-300 px-3 py-1 dark:border-slate-600"
            >
              Today
            </button>
          </>
        ) : (
          <>
            <label className="flex items-center gap-2">
              <span className="sr-only">Month</span>
              <select
                data-testid="lookup-month-select"
                value={monthNumber}
                onChange={(event) => change({ mode: "month", month: `${monthYear}-${pad(Number(event.target.value))}` })}
                className={CONTROL}
              >
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <option key={m} value={m} disabled={monthYear === todayYear && m > todayMonth}>
                    {monthName(m)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2">
              <span className="sr-only">Year</span>
              <select
                data-testid="lookup-year-select"
                value={monthYear}
                onChange={(event) => {
                  const year = Number(event.target.value);
                  const month = year === todayYear ? Math.min(monthNumber, todayMonth) : monthNumber;
                  change({ mode: "month", month: `${year}-${pad(month)}` });
                }}
                className={CONTROL}
              >
                {years.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
      </div>

      <h3 data-testid="lookup-heading" className="font-medium">
        {data ? describeLookup(data) : query.isError ? "Balances" : "Loading balances…"}
      </h3>
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        Each figure is the balance at the end of that day, after that day&apos;s transactions.
      </p>

      {query.isError && !hideError && (
        <div data-testid="balances-error" role="alert" className="mb-3 text-sm text-red-600 dark:text-red-400">
          {balanceErrorMessage(query.error)}{" "}
          <button type="button" data-testid="balances-retry" onClick={() => query.refetch()} className="underline">
            Try again
          </button>
        </div>
      )}

      {data && (
        <div
          data-testid="balances-result"
          aria-busy={query.isFetching}
          className={`space-y-3 ${query.isPlaceholderData ? "opacity-60" : ""}`}
        >
          <IngestedThrough
            resolvedDate={data.resolvedDate}
            ingestedThroughDate={data.ingestedThroughDate}
            onJumpTo={(date) => change({ mode: "date", date })}
          />
          <UnlinkedNotice notice={data.unlinkedTransactions} />
          <BalancesTable response={data} onSetBalance={onSetBalance} />
        </div>
      )}
    </section>
  );
}
