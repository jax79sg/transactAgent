import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setToken } from "../src/api/client";
import { getServerVersion } from "../src/api/version";

describe("getServerVersion", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    setToken(null);
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("asks GET /version without needing a login and returns the answer as it is", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ version: "1.2.3" }), { status: 200, headers: { "content-type": "application/json" } }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await expect(getServerVersion()).resolves.toEqual({ version: "1.2.3" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(new URL(String(url)).pathname).toBe("/version");
    expect(init.method).toBe("GET");
    expect((init.headers as Record<string, string>)["Authorization"]).toBeUndefined();
  });
});
