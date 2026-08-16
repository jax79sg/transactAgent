import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as backupApi from "../src/api/backup";
import * as recategorizationApi from "../src/api/recategorization";
import type {
  BackupStatusResponse,
  DisagreementDTO,
  DisagreementPage,
  ProposalDTO,
  ProposalPage,
} from "../src/api/types";
import { ReviewPage } from "../src/pages/ReviewPage";

vi.mock("../src/api/recategorization");
vi.mock("../src/api/backup");

const NO_BACKUPS_YET: BackupStatusResponse = {
  lastRunAt: null,
  outcome: null,
  failureCategory: null,
  transactionCount: null,
  backupFilename: null,
};

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
      embeddingStatus: "pending",
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

function makeDisagreement(overrides: Partial<DisagreementDTO> = {}): DisagreementDTO {
  return {
    id: "disagreement-1",
    candidateTransaction: {
      id: "txn-2",
      transactionDate: "2026-01-15",
      description: "NTUC FAIRPRICE #124",
      outFlow: "10.00",
      inFlow: null,
      currency: "SGD",
      bankName: "DBS",
      category: { id: "cat-unsure", name: "UNSURE" },
      categorySource: "unsure",
      convertedAmountSgd: "10.00",
      conversionIsApproximate: false,
      conversionUnavailable: false,
      bankStatementId: "stmt-2",
      embeddingStatus: "pending",
    },
    similarityCategory: { id: "cat-groceries", name: "Groceries" },
    llmCategory: { id: "cat-dining", name: "Dining" },
    similarityScore: "88.00",
    status: "pending",
    resolvedCategory: null,
    createdAt: "2026-01-16T00:00:00Z",
    ...overrides,
  };
}

function disagreementPageOf(items: DisagreementDTO[]): DisagreementPage {
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
  beforeEach(() => {
    // Sane default so tests that don't care about backup status aren't affected;
    // tests that do care override with their own mockResolvedValue.
    vi.spyOn(backupApi, "getBackupStatus").mockResolvedValue(NO_BACKUPS_YET);
    // Same reasoning: DisagreementTable now always queries on render (Matching
    // Precision Refinement) -- default to empty so it renders nothing and
    // pre-existing proposal-focused tests are unaffected; tests exercising it
    // override with their own mockResolvedValue.
    vi.spyOn(recategorizationApi, "listPendingDisagreements").mockResolvedValue(disagreementPageOf([]));
  });

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

  describe("BackupStatusPanel", () => {
    it("shows a neutral message when no backup has run yet", async () => {
      vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([]));
      vi.spyOn(backupApi, "getBackupStatus").mockResolvedValue(NO_BACKUPS_YET);
      renderReviewPage();

      await waitFor(() => {
        expect(screen.getByTestId("backup-status-none")).toHaveTextContent("No backups yet");
      });
    });

    it("shows the last backup time and transaction count on success", async () => {
      vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([]));
      vi.spyOn(backupApi, "getBackupStatus").mockResolvedValue({
        lastRunAt: "2026-08-08T02:00:00Z",
        outcome: "success",
        failureCategory: null,
        transactionCount: 2174,
        backupFilename: "transactions-backup-20260808T020000Z.csv",
      });
      renderReviewPage();

      await waitFor(() => {
        expect(screen.getByTestId("backup-status-success")).toHaveTextContent("2174 transactions");
      });
    });

    it("prompts to reconnect Google Drive on a drive_connectivity failure", async () => {
      vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([]));
      vi.spyOn(backupApi, "getBackupStatus").mockResolvedValue({
        lastRunAt: "2026-08-08T02:00:00Z",
        outcome: "failed",
        failureCategory: "drive_connectivity",
        transactionCount: null,
        backupFilename: null,
      });
      renderReviewPage();

      await waitFor(() => {
        const panel = screen.getByTestId("backup-status-failed-drive");
        expect(panel).toHaveTextContent("isn't connected");
        expect(screen.getByRole("link", { name: /reconnect google drive/i })).toHaveAttribute("href", "/settings");
      });
    });

    it("shows a generic failure indicator for a non-drive failure", async () => {
      vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([]));
      vi.spyOn(backupApi, "getBackupStatus").mockResolvedValue({
        lastRunAt: "2026-08-08T02:00:00Z",
        outcome: "failed",
        failureCategory: "other",
        transactionCount: null,
        backupFilename: null,
      });
      renderReviewPage();

      await waitFor(() => {
        expect(screen.getByTestId("backup-status-failed-other")).toHaveTextContent("Last backup failed");
      });
    });

    it("is visually separate from the proposal table", async () => {
      vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([makeProposal()]));
      renderReviewPage();

      await waitFor(() => {
        expect(screen.getByTestId("backup-status-panel")).toBeInTheDocument();
        expect(screen.getByTestId("review-row-proposal-1")).toBeInTheDocument();
      });
      // Two independent sections, not nested inside one another.
      expect(screen.getByTestId("backup-status-panel")).not.toContainElement(
        screen.getByTestId("review-row-proposal-1"),
      );
    });
  });

  describe("DisagreementTable", () => {
    it("renders nothing when there are no pending disagreements", async () => {
      vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([]));
      renderReviewPage();

      await waitFor(() => expect(screen.getByTestId("review-empty-state")).toBeInTheDocument());
      expect(screen.queryByTestId("disagreement-section")).not.toBeInTheDocument();
    });

    it("renders a disagreement row with both candidate categories and the score", async () => {
      vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([]));
      vi.spyOn(recategorizationApi, "listPendingDisagreements").mockResolvedValue(
        disagreementPageOf([makeDisagreement()]),
      );
      renderReviewPage();

      await waitFor(() => expect(screen.getByTestId("disagreement-row-disagreement-1")).toBeInTheDocument());
      const row = screen.getByTestId("disagreement-row-disagreement-1");
      expect(row).toHaveTextContent("NTUC FAIRPRICE #124");
      expect(row).toHaveTextContent("Groceries");
      expect(row).toHaveTextContent("Dining");
      expect(row).toHaveTextContent("88.00");
    });

    it("resolves a disagreement by choosing the similarity category", async () => {
      const user = userEvent.setup();
      vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([]));
      vi.spyOn(recategorizationApi, "listPendingDisagreements").mockResolvedValue(
        disagreementPageOf([makeDisagreement()]),
      );
      const resolveSpy = vi.spyOn(recategorizationApi, "resolveDisagreement").mockResolvedValue(makeDisagreement());
      renderReviewPage();

      await waitFor(() => expect(screen.getByTestId("disagreement-use-similarity-disagreement-1")).toBeInTheDocument());
      await user.click(screen.getByTestId("disagreement-use-similarity-disagreement-1"));

      await waitFor(() => {
        expect(resolveSpy).toHaveBeenCalledWith("disagreement-1", "cat-groceries");
      });
    });

    it("resolves a disagreement by choosing the LLM category", async () => {
      const user = userEvent.setup();
      vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([]));
      vi.spyOn(recategorizationApi, "listPendingDisagreements").mockResolvedValue(
        disagreementPageOf([makeDisagreement()]),
      );
      const resolveSpy = vi.spyOn(recategorizationApi, "resolveDisagreement").mockResolvedValue(makeDisagreement());
      renderReviewPage();

      await waitFor(() => expect(screen.getByTestId("disagreement-use-llm-disagreement-1")).toBeInTheDocument());
      await user.click(screen.getByTestId("disagreement-use-llm-disagreement-1"));

      await waitFor(() => {
        expect(resolveSpy).toHaveBeenCalledWith("disagreement-1", "cat-dining");
      });
    });

    it("rejects a disagreement", async () => {
      const user = userEvent.setup();
      vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([]));
      vi.spyOn(recategorizationApi, "listPendingDisagreements").mockResolvedValue(
        disagreementPageOf([makeDisagreement()]),
      );
      const rejectSpy = vi.spyOn(recategorizationApi, "rejectDisagreement").mockResolvedValue(makeDisagreement());
      renderReviewPage();

      await waitFor(() => expect(screen.getByTestId("disagreement-reject-disagreement-1")).toBeInTheDocument());
      await user.click(screen.getByTestId("disagreement-reject-disagreement-1"));

      await waitFor(() => {
        expect(rejectSpy).toHaveBeenCalledWith("disagreement-1", expect.anything());
      });
    });

    it("has no select-all or bulk action controls", async () => {
      vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([]));
      vi.spyOn(recategorizationApi, "listPendingDisagreements").mockResolvedValue(
        disagreementPageOf([makeDisagreement()]),
      );
      renderReviewPage();

      await waitFor(() => expect(screen.getByTestId("disagreement-section")).toBeInTheDocument());
      // Application Design Decision 2: no bulk actions for disagreements.
      expect(screen.getByTestId("disagreement-section")).not.toHaveTextContent("Select all");
    });

    it("is visually separate from the proposal table", async () => {
      vi.spyOn(recategorizationApi, "listPendingProposals").mockResolvedValue(pageOf([makeProposal()]));
      vi.spyOn(recategorizationApi, "listPendingDisagreements").mockResolvedValue(
        disagreementPageOf([makeDisagreement()]),
      );
      renderReviewPage();

      await waitFor(() => {
        expect(screen.getByTestId("disagreement-section")).toBeInTheDocument();
        expect(screen.getByTestId("review-row-proposal-1")).toBeInTheDocument();
      });
      expect(screen.getByTestId("disagreement-section")).not.toContainElement(
        screen.getByTestId("review-row-proposal-1"),
      );
    });
  });
});
