import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as dashboardsApi from "../src/api/dashboards";
import * as recurringPaymentsApi from "../src/api/recurringPayments";
import type { DetectionSuggestionDTO, RecurringPaymentDTO, RecurringPaymentMatchDTO } from "../src/api/types";
import { DashboardPage } from "../src/pages/DashboardPage";

vi.mock("../src/api/dashboards");
vi.mock("../src/api/recurringPayments");

function makePayment(overrides: Partial<RecurringPaymentDTO> = {}): RecurringPaymentDTO {
  return {
    id: "payment-1",
    name: "Gym Membership",
    expectedAmount: "80.00",
    frequency: "monthly",
    dueMonth: null,
    dueDay: 15,
    category: null,
    isTrusted: false,
    status: "due_soon",
    monthlySetAside: null,
    ...overrides,
  };
}

function makeMatch(overrides: Partial<RecurringPaymentMatchDTO> = {}): RecurringPaymentMatchDTO {
  return {
    id: "match-1",
    recurringPayment: { id: "payment-1", name: "Gym Membership" },
    transaction: {
      id: "txn-1",
      transactionDate: "2026-08-15",
      description: "GYM MEMBERSHIP FEE",
      outFlow: "80.00",
      inFlow: null,
      currency: "SGD",
      bankName: "DBS",
      category: { id: "cat-1", name: "Health" },
      categorySource: "similarity",
      convertedAmountSgd: "80.00",
      conversionIsApproximate: false,
      conversionUnavailable: false,
      bankStatementId: "stmt-1",
      embeddingStatus: "pending",
    },
    cyclePeriod: "2026-08",
    status: "pending",
    amountAtMatch: "80.00",
    createdAt: "2026-08-15T00:00:00Z",
    ...overrides,
  };
}

function makeSuggestion(overrides: Partial<DetectionSuggestionDTO> = {}): DetectionSuggestionDTO {
  return {
    id: "suggestion-1",
    descriptionPattern: "STREAMING SERVICE",
    suggestedAmount: "15.00",
    suggestedCategory: null,
    occurrenceCount: 2,
    status: "new",
    ...overrides,
  };
}

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openRecurringPaymentsTab(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByText("Recurring Payments"));
}

describe("DashboardPage Recurring Payments tab", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    const disclosure = { approximateCount: 0, excludedCount: 0, excludedTransactionIds: [] };
    vi.spyOn(dashboardsApi, "getCategoryTrends").mockResolvedValue({ series: [], disclosure });
    vi.spyOn(dashboardsApi, "getCashFlow").mockResolvedValue({ series: [], disclosure });
    vi.spyOn(dashboardsApi, "getBankBreakdown").mockResolvedValue({ series: [], disclosure });
  });

  it("shows empty states when nothing exists yet", async () => {
    vi.spyOn(recurringPaymentsApi, "listRecurringPayments").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listPendingMatches").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listDetectionSuggestions").mockResolvedValue([]);
    const user = userEvent.setup();
    renderDashboard();

    await openRecurringPaymentsTab(user);

    await waitFor(() => {
      expect(screen.getByTestId("recurring-payments-empty-state")).toBeInTheDocument();
    });
    expect(screen.getByTestId("pending-matches-empty-state")).toBeInTheDocument();
    expect(screen.getByTestId("suggestions-empty-state")).toBeInTheDocument();
  });

  it("renders a payment row with its status badge", async () => {
    vi.spyOn(recurringPaymentsApi, "listRecurringPayments").mockResolvedValue([makePayment({ status: "overdue" })]);
    vi.spyOn(recurringPaymentsApi, "listPendingMatches").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listDetectionSuggestions").mockResolvedValue([]);
    const user = userEvent.setup();
    renderDashboard();

    await openRecurringPaymentsTab(user);

    await waitFor(() => {
      expect(screen.getByTestId("recurring-payment-row-payment-1")).toHaveTextContent("Gym Membership");
    });
    expect(screen.getByTestId("status-badge-overdue")).toBeInTheDocument();
  });

  it("submits the add-payment form", async () => {
    vi.spyOn(recurringPaymentsApi, "listRecurringPayments").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listPendingMatches").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listDetectionSuggestions").mockResolvedValue([]);
    const createSpy = vi.spyOn(recurringPaymentsApi, "createRecurringPayment").mockResolvedValue(makePayment());
    const user = userEvent.setup();
    renderDashboard();

    await openRecurringPaymentsTab(user);
    await waitFor(() => expect(screen.getByTestId("new-recurring-payment-name")).toBeInTheDocument());

    await user.type(screen.getByTestId("new-recurring-payment-name"), "Gym Membership");
    await user.type(screen.getByTestId("new-recurring-payment-amount"), "80.00");
    await user.type(screen.getByTestId("new-recurring-payment-due-day"), "15");
    await user.click(screen.getByTestId("add-recurring-payment-button"));

    await waitFor(() => {
      expect(createSpy.mock.calls[0]?.[0]).toEqual(
        expect.objectContaining({ name: "Gym Membership", expectedAmount: "80.00", dueDay: 15 }),
      );
    });
  });

  it("approves a pending match", async () => {
    vi.spyOn(recurringPaymentsApi, "listRecurringPayments").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listPendingMatches").mockResolvedValue([makeMatch()]);
    vi.spyOn(recurringPaymentsApi, "listDetectionSuggestions").mockResolvedValue([]);
    const approveSpy = vi.spyOn(recurringPaymentsApi, "approveMatch").mockResolvedValue(makeMatch({ status: "approved" }));
    const user = userEvent.setup();
    renderDashboard();

    await openRecurringPaymentsTab(user);
    await waitFor(() => expect(screen.getByTestId("approve-match-match-1")).toBeInTheDocument());
    await user.click(screen.getByTestId("approve-match-match-1"));

    await waitFor(() => {
      expect(approveSpy.mock.calls[0]?.[0]).toBe("match-1");
    });
  });

  it("rejects a pending match", async () => {
    vi.spyOn(recurringPaymentsApi, "listRecurringPayments").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listPendingMatches").mockResolvedValue([makeMatch()]);
    vi.spyOn(recurringPaymentsApi, "listDetectionSuggestions").mockResolvedValue([]);
    const rejectSpy = vi.spyOn(recurringPaymentsApi, "rejectMatch").mockResolvedValue(makeMatch({ status: "rejected" }));
    const user = userEvent.setup();
    renderDashboard();

    await openRecurringPaymentsTab(user);
    await waitFor(() => expect(screen.getByTestId("reject-match-match-1")).toBeInTheDocument());
    await user.click(screen.getByTestId("reject-match-match-1"));

    await waitFor(() => {
      expect(rejectSpy.mock.calls[0]?.[0]).toBe("match-1");
    });
  });

  it("adds a detected suggestion as a recurring payment", async () => {
    vi.spyOn(recurringPaymentsApi, "listRecurringPayments").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listPendingMatches").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listDetectionSuggestions").mockResolvedValue([makeSuggestion()]);
    const addSpy = vi.spyOn(recurringPaymentsApi, "addFromDetectionSuggestion").mockResolvedValue(makePayment());
    const user = userEvent.setup();
    renderDashboard();

    await openRecurringPaymentsTab(user);
    await waitFor(() => expect(screen.getByTestId("add-suggestion-suggestion-1")).toBeInTheDocument());
    await user.click(screen.getByTestId("add-suggestion-suggestion-1"));

    await waitFor(() => {
      expect(addSpy.mock.calls[0]?.[0]).toBe("suggestion-1");
    });
  });

  it("dismisses a detected suggestion", async () => {
    vi.spyOn(recurringPaymentsApi, "listRecurringPayments").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listPendingMatches").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listDetectionSuggestions").mockResolvedValue([makeSuggestion()]);
    const dismissSpy = vi.spyOn(recurringPaymentsApi, "dismissDetectionSuggestion").mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderDashboard();

    await openRecurringPaymentsTab(user);
    await waitFor(() => expect(screen.getByTestId("dismiss-suggestion-suggestion-1")).toBeInTheDocument());
    await user.click(screen.getByTestId("dismiss-suggestion-suggestion-1"));

    await waitFor(() => {
      expect(dismissSpy.mock.calls[0]?.[0]).toBe("suggestion-1");
    });
  });

  it("parses and submits bulk-import rows", async () => {
    vi.spyOn(recurringPaymentsApi, "listRecurringPayments").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listPendingMatches").mockResolvedValue([]);
    vi.spyOn(recurringPaymentsApi, "listDetectionSuggestions").mockResolvedValue([]);
    const bulkSpy = vi.spyOn(recurringPaymentsApi, "bulkImportRecurringPayments").mockResolvedValue({ created: [], failed: [] });
    const user = userEvent.setup();
    renderDashboard();

    await openRecurringPaymentsTab(user);
    await waitFor(() => expect(screen.getByTestId("bulk-import-textarea")).toBeInTheDocument());

    await user.type(screen.getByTestId("bulk-import-textarea"), "Gym Membership, 80.00, monthly, 15");
    await user.click(screen.getByTestId("bulk-import-button"));

    await waitFor(() => {
      expect(bulkSpy.mock.calls[0]?.[0]).toEqual([
        expect.objectContaining({ name: "Gym Membership", amount: "80.00", frequency: "monthly", dueDay: "15" }),
      ]);
    });
  });
});
