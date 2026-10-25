import { render, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const SESSION_STORAGE_KEY = "transactagent_token";

// A page asks for its data from an effect on its first render. React runs a child's effects before its parent's, so
// this request goes out before AuthProvider's own effects have run: the token must already be in place by then.
// The API client keeps its token and its 401 handler at module level, so each test loads both modules afresh, as a
// real page load does; otherwise the previous test's provider would leave its handlers behind.
async function renderFreshPage() {
  vi.resetModules();
  const { apiRequest } = await import("../src/api/client");
  const { AuthProvider } = await import("../src/context/AuthContext");

  function FirstRenderRequest() {
    useEffect(() => {
      void apiRequest("/categories").catch(() => {});
    }, []);
    return null;
  }

  return render(
    <AuthProvider>
      <FirstRenderRequest />
    </AuthProvider>,
  );
}

describe("AuthProvider on a full page load", () => {
  const originalFetch = globalThis.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sessionStorage.clear();
    // The API answers 401 to a request with no bearer token, as the real one does.
    fetchMock = vi.fn(async (_url: unknown, init: { headers: Record<string, string> }) =>
      init.headers["Authorization"]
        ? new Response("[]", { status: 200, headers: { "content-type": "application/json" } })
        : new Response(JSON.stringify({ error: "unauthorized", message: "Unauthorized" }), { status: 401 }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("sends the saved token with a page's very first request", async () => {
    sessionStorage.setItem(SESSION_STORAGE_KEY, "saved-token");

    await renderFreshPage();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer saved-token");
  });

  it("keeps the session after a reload instead of logging the user out", async () => {
    sessionStorage.setItem(SESSION_STORAGE_KEY, "saved-token");

    await renderFreshPage();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await fetchMock.mock.results[0].value; // the response, and so any 401 handling, has been delivered
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBe("saved-token");
  });

  it("sends no Authorization header when nobody is signed in", async () => {
    await renderFreshPage();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["Authorization"]).toBeUndefined();
  });
});
