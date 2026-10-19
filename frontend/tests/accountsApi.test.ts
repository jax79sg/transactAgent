import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { listAccounts, mergeAccounts, setAnchor, updateAccount } from "../src/api/accounts";
import { setToken } from "../src/api/client";

// Epic 13: one function per account endpoint, with the method, path and body the API design fixes.
describe("accounts API module", () => {
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
    return { path: parsed.pathname, search: parsed.search, method: init.method as string, body: init.body as string | undefined };
  }

  it("lists accounts with GET /accounts", async () => {
    await listAccounts();
    expect(lastCall()).toEqual({ path: "/accounts", search: "", method: "GET", body: undefined });
  });

  it("renames with PATCH /accounts/{id} and sends only the field it was given", async () => {
    await updateAccount("a-1", { name: "Holiday fund" });
    const call = lastCall();
    expect([call.path, call.method]).toEqual(["/accounts/a-1", "PATCH"]);
    expect(JSON.parse(call.body!)).toEqual({ name: "Holiday fund" });
  });

  it("retypes with PATCH and sends only the type", async () => {
    await updateAccount("a-1", { type: "credit_card" });
    expect(JSON.parse(lastCall().body!)).toEqual({ type: "credit_card" });
  });

  it("sets an anchor with PUT /accounts/{id}/anchor, the balance staying a string", async () => {
    await setAnchor("a-1", { balance: "1234.50", asOfDate: "2026-10-18" });
    const call = lastCall();
    expect([call.path, call.method]).toEqual(["/accounts/a-1/anchor", "PUT"]);
    expect(JSON.parse(call.body!)).toEqual({ balance: "1234.50", asOfDate: "2026-10-18" });
  });

  it("merges with POST to the SURVIVOR's path, naming the absorbed account", async () => {
    await mergeAccounts("keep-1", { absorbedAccountId: "gone-2", keepAnchorFrom: "keep-1" });
    const call = lastCall();
    expect([call.path, call.method]).toEqual(["/accounts/keep-1/merge", "POST"]);
    expect(JSON.parse(call.body!)).toEqual({ absorbedAccountId: "gone-2", keepAnchorFrom: "keep-1" });
  });

  it("leaves keepAnchorFrom out of a merge that has no choice to make", async () => {
    await mergeAccounts("keep-1", { absorbedAccountId: "gone-2" });
    expect(JSON.parse(lastCall().body!)).toEqual({ absorbedAccountId: "gone-2" });
  });
});
