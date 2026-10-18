import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiRequest, ApiError, registerAuthHandlers, setToken, toSnakeCase } from "../src/api/client";

describe("toSnakeCase", () => {
  it("converts camelCase keys to snake_case", () => {
    expect(toSnakeCase("dateFrom")).toBe("date_from");
    expect(toSnakeCase("categorySource")).toBe("category_source");
    expect(toSnakeCase("pageSize")).toBe("page_size");
    expect(toSnakeCase("page")).toBe("page"); // no-op for already-lowercase keys
  });
});

describe("apiRequest", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    setToken("test-token");
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("sends the Authorization header when a token is set", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await apiRequest("/categories");

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer test-token");
  });

  it("converts camelCase query keys to snake_case in the request URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await apiRequest("/transactions", { query: { dateFrom: "2026-01-01", pageSize: 50 } });

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("date_from=2026-01-01");
    expect(String(url)).toContain("page_size=50");
  });

  it("calls the registered onUnauthorized handler and throws ApiError on 401", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: "unauthorized", message: "Token expired" }), { status: 401 }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const onUnauthorized = vi.fn();
    registerAuthHandlers(() => "test-token", onUnauthorized);

    await expect(apiRequest("/transactions")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("throws ApiError with the response body on non-2xx responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: "duplicate_category_name", message: "already exists" }), {
        status: 400,
      }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await expect(apiRequest("/categories", { method: "POST", body: { name: "x" } })).rejects.toMatchObject({
      status: 400,
      body: { error: "duplicate_category_name" },
    });
  });

  // Epic 13: the account rename/retype call is a PATCH, which the client did not offer before.
  it("sends a PATCH with a JSON body and the content type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await apiRequest("/accounts/abc", { method: "PATCH", body: { name: "Savings" } });

    const [url, init] = fetchMock.mock.calls[0];
    expect(new URL(String(url)).pathname).toBe("/accounts/abc");
    expect(init.method).toBe("PATCH");
    expect(init.body).toBe(JSON.stringify({ name: "Savings" }));
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });
});
