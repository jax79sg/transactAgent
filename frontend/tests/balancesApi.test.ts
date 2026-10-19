import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getBalances, getBalanceSeries, getDiscrepancies } from "../src/api/balances";
import { setToken } from "../src/api/client";

// Epic 13: the three read endpoints, with the query names the API reads (`date`, `month`, `from`, `to`, `granularity`).
describe("balances API module", () => {
  const originalFetch = globalThis.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    setToken("test-token");
    fetchMock = vi.fn().mockImplementation(async () => new Response("{}", { status: 200 })); // a fresh body per call
    globalThis.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  function lastCall() {
    const [url, init] = fetchMock.mock.calls[0];
    const parsed = new URL(String(url));
    return { path: parsed.pathname, query: Object.fromEntries(parsed.searchParams), method: init.method as string };
  }

  it("looks up a date with GET /balances?date=", async () => {
    await getBalances({ date: "2026-07-31" });
    expect(lastCall()).toEqual({ path: "/balances", query: { date: "2026-07-31" }, method: "GET" });
  });

  it("looks up a month with GET /balances?month=", async () => {
    await getBalances({ month: "2026-10" });
    expect(lastCall()).toEqual({ path: "/balances", query: { month: "2026-10" }, method: "GET" });
  });

  it("asks for the series with no query at all when no dates are given, so the API supplies the last 12 months", async () => {
    await getBalanceSeries();
    expect(lastCall()).toEqual({ path: "/balances/series", query: {}, method: "GET" });
  });

  it("passes from, to and granularity unchanged", async () => {
    await getBalanceSeries({ from: "2026-05-01", to: "2026-10-18", granularity: "month" });
    expect(lastCall().query).toEqual({ from: "2026-05-01", to: "2026-10-18", granularity: "month" });
  });

  it("leaves out whatever is not given", async () => {
    await getBalanceSeries({ granularity: "day" });
    expect(lastCall().query).toEqual({ granularity: "day" });
    fetchMock.mockClear();
    await getBalanceSeries({ from: "2026-05-01" });
    expect(lastCall().query).toEqual({ from: "2026-05-01" });
  });

  it("reads the discrepancies with GET /balances/discrepancies", async () => {
    await getDiscrepancies();
    expect(lastCall()).toEqual({ path: "/balances/discrepancies", query: {}, method: "GET" });
  });
});
