import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setToken } from "../src/api/client";
import { getCosts } from "../src/api/costs";

describe("getCosts", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    setToken("test-token");
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("asks GET /costs with every choice as the snake_case query names the API reads, time zone included", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await getCosts({
      dateFrom: "2026-09-08",
      dateTo: "2026-10-07",
      granularity: "week",
      groupBy: "model",
      timezone: "Asia/Singapore",
    });

    const [url, init] = fetchMock.mock.calls[0];
    const parsed = new URL(String(url));
    expect(parsed.pathname).toBe("/costs");
    expect(init.method).toBe("GET");
    expect(Object.fromEntries(parsed.searchParams)).toEqual({
      date_from: "2026-09-08",
      date_to: "2026-10-07",
      granularity: "week",
      group_by: "model",
      timezone: "Asia/Singapore",
    });
  });

  it("returns the API's answer as it is", async () => {
    const answer = { currency: "USD", periods: ["2026-10-07"] };
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(answer), { status: 200, headers: { "content-type": "application/json" } }),
    ) as unknown as typeof fetch;

    await expect(
      getCosts({ dateFrom: "2026-10-07", dateTo: "2026-10-07", granularity: "day", groupBy: "none", timezone: "UTC" }),
    ).resolves.toEqual(answer);
  });
});
