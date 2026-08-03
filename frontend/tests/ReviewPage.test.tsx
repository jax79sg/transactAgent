import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as recategorizationApi from "../src/api/recategorization";
import type { ProposalDTO, ProposalPage } from "../src/api/types";
import { ReviewPage } from "../src/pages/ReviewPage";

vi.mock("../src/api/recategorization");

function makeProposal(overrides: Partial<ProposalDTO> = {}): ProposalDTO {
  return {
    id: "proposal-1",
    candidateTransaction: {
      id: "txn-1",
      transactionDate: "2026-01-15",
      description: "IKEA FURNITURE STORE #2",
      outFlow: "42.00",
      inFlow: null,
      currency: "SGD",
      bankName: "DBS",
      category: { id: "cat-unsure", name: "UNSURE" },
      categorySource: "unsure",
      convertedAmountSgd: "42.00",
      conversionIsApproximate: false,
      conversionUnavailable: false,
      bankStatementId: "stmt-1",
    },
    proposedCategory: { id: "cat-household", name: "Household" },
    matchScore: "93.02",
    sourceBucket: "unsure",
    status: "pending",
    createdAt: "2026-01-16T00:00:00Z",
    sourceTransactionId: "txn-0",
    ...overrides,
  };
}

function pageOf(items: ProposalDTO[]): ProposalPage {
  return { items, page: 1, pageSize: 20, totalCount: items.length };
}

function renderReviewPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ReviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ReviewPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows an empty state when there are no pending proposals", async () => {
    vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([]));
    renderReviewPage();

    await waitFor(() => {
      expect(screen.getByTestId("review-empty-state")).toBeInTheDocument();
    });
  });

  it("renders a proposal row with candidate, proposed category, score, and source bucket", async () => {
    vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([makeProposal()]));
    renderReviewPage();

    await waitFor(() => {
      expect(screen.getByTestId("review-row-proposal-1")).toBeInTheDocument();
    });
    const row = screen.getByTestId("review-row-proposal-1");
    expect(row).toHaveTextContent("IKEA FURNITURE STORE #2");
    expect(row).toHaveTextContent("UNSURE");
    expect(row).toHaveTextContent("Household");
    expect(row).toHaveTextContent("93.02");
    expect(row).toHaveTextContent("Unsure");
  });

  it("labels an already-categorized-bucket proposal distinctly", async () => {
    vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(
      pageOf([makeProposal({ sourceBucket: "categorized" })]),
    );
    renderReviewPage();

    await waitFor(() => {
      expect(screen.getByTestId("review-row-proposal-1")).toHaveTextContent("Already categorized");
    });
  });

  it("approves a single proposal", async () => {
    const user = userEvent.setup();
    vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([makeProposal()]));
    const approveSpy = vi.spyOn(recategorizationApi, "approveProposal").mockResolvedValue(makeProposal());
    renderReviewPage();

    await waitFor(() => expect(screen.getByTestId("review-approve-proposal-1")).toBeInTheDocument());
    await user.click(screen.getByTestId("review-approve-proposal-1"));

    await waitFor(() => {
      // TanStack Query v5 calls mutationFn(variables, context) internally -- the
      // second arg is React Query's own context object, not something this
      // component controls, so only the first (real) argument is asserted.
      expect(approveSpy).toHaveBeenCalledWith("proposal-1", expect.anything());
    });
  });

  it("rejects a single proposal", async () => {
    const user = userEvent.setup();
    vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([makeProposal()]));
    const rejectSpy = vi.spyOn(recategorizationApi, "rejectProposal").mockResolvedValue(makeProposal());
    renderReviewPage();

    await waitFor(() => expect(screen.getByTestId("review-reject-proposal-1")).toBeInTheDocument());
    await user.click(screen.getByTestId("review-reject-proposal-1"));

    await waitFor(() => {
      expect(rejectSpy).toHaveBeenCalledWith("proposal-1", expect.anything());
    });
  });

  it("selects all and bulk-approves the current page's proposals", async () => {
    const user = userEvent.setup();
    const proposals = [makeProposal({ id: "p1" }), makeProposal({ id: "p2" })];
    vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf(proposals));
    const bulkApproveSpy = vi
      .spyOn(recategorizationApi, "bulkApproveProposals")
      .mockResolvedValue({ approvedIds: ["p1", "p2"], failedIds: [] });
    renderReviewPage();

    await waitFor(() => expect(screen.getByTestId("review-select-all")).toBeInTheDocument());
    await user.click(screen.getByTestId("review-select-all"));
    await user.click(screen.getByTestId("review-bulk-approve"));

    await waitFor(() => {
      expect(bulkApproveSpy).toHaveBeenCalledWith(expect.arrayContaining(["p1", "p2"]), expect.anything());
    });
  });

  it("shows an inline notice for proposals that fail a bulk action", async () => {
    const user = userEvent.setup();
    const proposals = [makeProposal({ id: "p1" }), makeProposal({ id: "p2" })];
    vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf(proposals));
    vi.spyOn(recategorizationApi, "bulkApproveProposals").mockResolvedValue({
      approvedIds: ["p1"],
      failedIds: ["p2"],
    });
    renderReviewPage();

    await waitFor(() => expect(screen.getByTestId("review-select-all")).toBeInTheDocument());
    await user.click(screen.getByTestId("review-select-all"));
    await user.click(screen.getByTestId("review-bulk-approve"));

    await waitFor(() => {
      expect(screen.getByTestId("review-failed-p2")).toHaveTextContent("already been resolved");
    });
  });

  it("bulk action buttons are disabled until something is selected", async () => {
    vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([makeProposal()]));
    renderReviewPage();

    await waitFor(() => expect(screen.getByTestId("review-bulk-approve")).toBeInTheDocument());
    expect(screen.getByTestId("review-bulk-approve")).toBeDisabled();
    expect(screen.getByTestId("review-bulk-reject")).toBeDisabled();
  });
});
