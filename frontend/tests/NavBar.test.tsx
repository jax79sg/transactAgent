import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as recategorizationApi from "../src/api/recategorization";
import { NavBar } from "../src/components/NavBar";
import { AuthProvider } from "../src/context/AuthContext";

vi.mock("../src/api/recategorization");

function renderNavBar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthProvider>
          <NavBar />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NavBar pending review badge", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows no badge when there are zero pending proposals", async () => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 0 });
    renderNavBar();

    await waitFor(() => {
      expect(recategorizationApi.getPendingCount).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("pending-review-badge")).not.toBeInTheDocument();
  });

  it("shows the pending count when proposals are waiting", async () => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 4 });
    renderNavBar();

    await waitFor(() => {
      expect(screen.getByTestId("pending-review-badge")).toHaveTextContent("4");
    });
  });

  it("includes a Review nav link", () => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 0 });
    renderNavBar();

    expect(screen.getByText("Review")).toBeInTheDocument();
  });
});
