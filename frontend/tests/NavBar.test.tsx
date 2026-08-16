import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as recategorizationApi from "../src/api/recategorization";
import * as recurringPaymentsApi from "../src/api/recurringPayments";
import { NavBar } from "../src/components/NavBar";
import { AuthProvider } from "../src/context/AuthContext";

vi.mock("../src/api/recategorization");
vi.mock("../src/api/recurringPayments");

const NO_ATTENTION_NEEDED = { dueSoonCount: 0, overdueCount: 0, pendingMatchCount: 0, newSuggestionCount: 0 };

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
  beforeEach(() => {
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue(NO_ATTENTION_NEEDED);
  });

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

describe("NavBar recurring payments badge", () => {
  beforeEach(() => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 0 });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows no badge when nothing needs attention", async () => {
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue(NO_ATTENTION_NEEDED);
    renderNavBar();

    await waitFor(() => {
      expect(recurringPaymentsApi.getRecurringPaymentsStatus).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("recurring-payments-badge")).not.toBeInTheDocument();
  });

  it("shows the combined overdue + pending + suggestion count", async () => {
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue({
      dueSoonCount: 3, overdueCount: 1, pendingMatchCount: 2, newSuggestionCount: 1,
    });
    renderNavBar();

    await waitFor(() => {
      expect(screen.getByTestId("recurring-payments-badge")).toHaveTextContent("4"); // 1 + 2 + 1, not dueSoonCount
    });
  });

  it("does not count dueSoonCount toward the badge", async () => {
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue({
      dueSoonCount: 5, overdueCount: 0, pendingMatchCount: 0, newSuggestionCount: 0,
    });
    renderNavBar();

    await waitFor(() => {
      expect(recurringPaymentsApi.getRecurringPaymentsStatus).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("recurring-payments-badge")).not.toBeInTheDocument();
  });
});
