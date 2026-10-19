import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as duplicatesApi from "../src/api/duplicates";
import { ApiError } from "../src/api/client";
import type { DuplicatePair, DuplicatePairPage, RemovalStatus } from "../src/api/types";
import { DuplicateStatementsPanel } from "../src/components/DuplicateStatementsPanel";
import { pair, preview, scan } from "./duplicatesFixtures";

vi.mock("../src/api/duplicates");

function pageOf(items: DuplicatePair[], totalCount = items.length): DuplicatePairPage {
  return { items, page: 1, pageSize: 20, totalCount };
}

function removal(status: RemovalStatus["status"], overrides: Partial<RemovalStatus> = {}): RemovalStatus {
  return { jobId: "job-1", status, failureReason: null, requestedAt: "2026-10-04T10:00:00Z", finishedAt: null, deletedCounts: null, ...overrides };
}

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DuplicateStatementsPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

function mockList(items: DuplicatePair[], totalCount?: number) {
  vi.spyOn(duplicatesApi, "listPairs").mockResolvedValue(pageOf(items, totalCount));
}

describe("DuplicateStatementsPanel", () => {
  beforeEach(() => {
    vi.spyOn(duplicatesApi, "getScanStatus").mockResolvedValue(scan());
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  describe("when there is nothing to decide", () => {
    it("says detection is switched off, with a link to Settings, when the setting is off", async () => {
      vi.spyOn(duplicatesApi, "getScanStatus").mockResolvedValue(scan({ detectionEnabled: false, lastCompletedAt: null, pairsFound: null }));
      mockList([]);
      renderPanel();

      expect(await screen.findByTestId("duplicates-off")).toHaveTextContent("Duplicate detection is switched off.");
      expect(screen.getByRole("link", { name: /Change it in Settings/ })).toHaveAttribute("href", "/settings");
      expect(screen.getByTestId("duplicates-scan-line")).toHaveTextContent("Not checked yet.");
      expect(screen.queryByTestId("duplicates-none")).not.toBeInTheDocument();
    });

    it("says none were found, with when it last looked, when detection is on", async () => {
      mockList([]);
      renderPanel();

      expect(await screen.findByTestId("duplicates-none")).toHaveTextContent("No probable duplicate statements.");
      expect(screen.getByTestId("duplicates-scan-line")).toHaveTextContent(/Last checked .*; 1 found\./);
      expect(screen.queryByTestId("duplicates-off")).not.toBeInTheDocument();
    });

    it("renders no group headings", async () => {
      mockList([]);
      renderPanel();
      await screen.findByTestId("duplicates-none");

      expect(screen.queryByTestId("duplicates-group-awaiting")).not.toBeInTheDocument();
      expect(screen.queryByTestId("duplicates-group-removing")).not.toBeInTheDocument();
      expect(screen.queryByTestId("duplicates-group-removed")).not.toBeInTheDocument();
    });
  });

  describe("a pair awaiting a decision", () => {
    it("shows the copy to keep, the copy to remove, their sizes and manual corrections, and a link to the comparison", async () => {
      mockList([pair()]);
      renderPanel();

      const row = await screen.findByTestId("duplicate-pair-pair-1");
      expect(within(screen.getByTestId("duplicates-group-awaiting")).getByRole("heading")).toHaveTextContent("Awaiting your decision");
      expect(row).toHaveTextContent("Keep");
      expect(row).toHaveTextContent("JUN 2026_0728.pdf (UOB, 2 Jun to 30 Jun 2026)");
      expect(row).toHaveTextContent("5 transactions; 2 manual corrections");
      expect(row).toHaveTextContent("JUN 2026_0828.pdf (UOB, 2 Jun to 30 Jun 2026)");
      expect(row).toHaveTextContent("5 transactions; 0 manual corrections");
      expect(screen.getByTestId("duplicate-view-pair-1")).toHaveAttribute("href", "/duplicates/cmp-1");
    });

    it("offers Remove duplicate and dismiss, and no 'swap' control (the user's alternative to the proposal is to dismiss)", async () => {
      mockList([pair()]);
      renderPanel();

      expect(await screen.findByTestId("duplicate-remove-pair-1")).toBeInTheDocument();
      expect(screen.getByTestId("duplicate-dismiss-pair-1")).toBeInTheDocument();
      expect(screen.queryByText(/swap/i)).not.toBeInTheDocument();
      expect(screen.queryByTestId("duplicate-info-only-pair-1")).not.toBeInTheDocument();
    });

    it("lists a pair of clearly different sizes for information only: dismiss, but NO remove action", async () => {
      mockList([pair({ removalOffered: false, preview: null })]);
      renderPanel();

      expect(await screen.findByTestId("duplicate-info-only-pair-1")).toHaveTextContent(
        "These statements differ in size, so this is listed for information only.",
      );
      expect(screen.queryByTestId("duplicate-remove-pair-1")).not.toBeInTheDocument();
      expect(screen.getByTestId("duplicate-dismiss-pair-1")).toBeInTheDocument();
      expect(screen.getByTestId("duplicate-view-pair-1")).toBeInTheDocument();
    });

    it("shows a pair with a missing statement as stale, with dismiss only", async () => {
      mockList([pair({ stale: true, removalOffered: false, preview: null, correctionsOnKept: null, correctionsOnRemoved: null })]);
      renderPanel();

      expect(await screen.findByTestId("duplicate-stale-pair-1")).toHaveTextContent("One of these statements no longer exists.");
      expect(screen.queryByTestId("duplicate-remove-pair-1")).not.toBeInTheDocument();
      expect(screen.queryByTestId("duplicate-info-only-pair-1")).not.toBeInTheDocument();
      expect(screen.getByTestId("duplicate-dismiss-pair-1")).toBeInTheDocument();
      expect(screen.getByTestId("duplicate-pair-pair-1")).not.toHaveTextContent("manual correction");
    });

    it("dismisses a pair and refreshes the list, the badge count and the scan status together", async () => {
      mockList([pair()]);
      const dismiss = vi.spyOn(duplicatesApi, "dismissPair").mockResolvedValue(pair({ status: "dismissed" }));
      const { queryClient } = renderPanel();
      const invalidate = vi.spyOn(queryClient, "invalidateQueries");
      const user = userEvent.setup();

      await user.click(await screen.findByTestId("duplicate-dismiss-pair-1"));

      await waitFor(() => expect(dismiss).toHaveBeenCalledWith("pair-1"));
      await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["duplicates"] })); // the prefix: pairs, pendingCount, scanStatus
    });

    it("shows a failed dismissal on the row, in plain words", async () => {
      mockList([pair()]);
      vi.spyOn(duplicatesApi, "dismissPair").mockRejectedValue(new ApiError(409, { error: "pair_not_pending", message: "x" }));
      renderPanel();
      const user = userEvent.setup();

      await user.click(await screen.findByTestId("duplicate-dismiss-pair-1"));

      expect(await screen.findByTestId("duplicate-error-pair-1")).toHaveTextContent("This pair has already been decided.");
    });
  });

  describe("confirming a removal", () => {
    async function openDialog(items: DuplicatePair[] = [pair({ preview: preview({ transactions: 5, statementSections: 1, recategorizationJobs: 2, onlyOnRemovedCopy: 1, correctionsLost: 2 }) })]) {
      mockList(items);
      const view = renderPanel();
      const user = userEvent.setup();
      await user.click(await screen.findByTestId(`duplicate-remove-${items[0].id}`));
      await screen.findByTestId("removal-dialog");
      return { ...view, user };
    }

    it("states exactly what will be permanently deleted, the embeddings, what exists only on this copy, and the corrections lost", async () => {
      await openDialog();

      const dialog = screen.getByTestId("removal-dialog");
      expect(dialog).toHaveTextContent("Permanently remove this duplicate?");
      expect(dialog).toHaveTextContent("JUN 2026_0828.pdf (UOB, 2 Jun to 30 Jun 2026)"); // the copy to remove
      const list = within(screen.getByTestId("removal-preview"));
      expect(list.getByText("5 transactions")).toBeInTheDocument();
      expect(list.getByText("1 account section")).toBeInTheDocument();
      expect(list.getByText("2 recategorization jobs")).toBeInTheDocument();
      expect(list.queryByText(/disagreement/)).not.toBeInTheDocument(); // zero kinds are not listed
      expect(dialog).toHaveTextContent("search embeddings are deleted too");
      expect(screen.getByTestId("removal-only-on-copy")).toHaveTextContent("1 transaction exists only on this copy and will be lost.");
      expect(screen.getByTestId("removal-corrections-lost")).toHaveTextContent("2 manual corrections on this copy will be lost.");
      expect(dialog).toHaveTextContent("The file in Google Drive is not touched.");
    });

    it("leaves out the two warnings when there is nothing to warn about", async () => {
      await openDialog([pair({ preview: preview({ onlyOnRemovedCopy: 0, correctionsLost: 0 }) })]);

      expect(screen.queryByTestId("removal-only-on-copy")).not.toBeInTheDocument();
      expect(screen.queryByTestId("removal-corrections-lost")).not.toBeInTheDocument();
    });

    it("cancel changes nothing", async () => {
      const remove = vi.spyOn(duplicatesApi, "requestRemoval");
      const { user } = await openDialog();

      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(screen.queryByTestId("removal-dialog")).not.toBeInTheDocument();
      expect(remove).not.toHaveBeenCalled();
    });

    it("sends the hash of the copy to remove and EXACTLY the correction count the dialog showed", async () => {
      const remove = vi.spyOn(duplicatesApi, "requestRemoval").mockResolvedValue(pair({ removal: removal("queued") }));
      const { user } = await openDialog();

      await user.click(screen.getByTestId("confirm-removal"));

      await waitFor(() => expect(remove).toHaveBeenCalledWith("pair-1", { removeStatementHash: "b".repeat(64), acknowledgedCorrectionsLost: 2 }));
      await waitFor(() => expect(screen.queryByTestId("removal-dialog")).not.toBeInTheDocument());
    });

    it("on success refreshes everything (list, badge, scan status)", async () => {
      vi.spyOn(duplicatesApi, "requestRemoval").mockResolvedValue(pair({ removal: removal("queued") }));
      const { queryClient, user } = await openDialog();
      const invalidate = vi.spyOn(queryClient, "invalidateQueries");

      await user.click(screen.getByTestId("confirm-removal"));

      await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["duplicates"] }));
    });

    it.each(["confirmation_out_of_date", "pair_not_pending", "removal_not_offered", "statement_missing", "removal_already_requested"])(
      "when the server says %s, the dialog closes, the list refreshes, a message says what happened, and nothing was deleted",
      async (code) => {
        const remove = vi.spyOn(duplicatesApi, "requestRemoval").mockRejectedValue(new ApiError(409, { error: code, message: "The numbers changed. Please review again." }));
        const { user } = await openDialog();
        const callsBefore = vi.mocked(duplicatesApi.listPairs).mock.calls.length;

        await user.click(screen.getByTestId("confirm-removal"));

        expect(await screen.findByTestId("duplicates-notice")).toBeInTheDocument();
        expect(screen.queryByTestId("removal-dialog")).not.toBeInTheDocument();
        await waitFor(() => expect(vi.mocked(duplicatesApi.listPairs).mock.calls.length).toBeGreaterThan(callsBefore));
        expect(remove).toHaveBeenCalledTimes(1);
      },
    );

    it("keeps the dialog open and shows an unexpected error inside it, so the user can retry or cancel", async () => {
      vi.spyOn(duplicatesApi, "requestRemoval").mockRejectedValue(new Error("network down"));
      const { user } = await openDialog();

      await user.click(screen.getByTestId("confirm-removal"));

      expect(await screen.findByTestId("removal-dialog-error")).toHaveTextContent("Something went wrong. Please try again.");
      expect(screen.getByTestId("removal-dialog")).toBeInTheDocument();
    });

    it("disables the destructive button while the request is in flight", async () => {
      let resolve: (p: DuplicatePair) => void = () => {};
      vi.spyOn(duplicatesApi, "requestRemoval").mockReturnValue(new Promise((r) => (resolve = r)));
      const { user } = await openDialog();

      await user.click(screen.getByTestId("confirm-removal"));

      await waitFor(() => expect(screen.getByTestId("confirm-removal")).toBeDisabled());
      resolve(pair({ removal: removal("queued") }));
      await waitFor(() => expect(screen.queryByTestId("removal-dialog")).not.toBeInTheDocument()); // let it settle inside the test
    });
  });

  describe("removal status and groups", () => {
    it.each([
      ["queued", "Removal requested -- waiting for the worker..."],
      ["running", "Removing..."],
      ["embeddings_pending", "Removed -- cleaning up search data..."],
    ] as const)("shows a %s removal under 'Being removed', without decision buttons", async (status, text) => {
      mockList([pair({ removal: removal(status) })]);
      renderPanel();

      expect(await screen.findByTestId("duplicate-removal-status-pair-1")).toHaveTextContent(text);
      expect(within(screen.getByTestId("duplicates-group-removing")).getByRole("heading")).toHaveTextContent("Being removed");
      expect(screen.queryByTestId("duplicates-group-awaiting")).not.toBeInTheDocument();
      expect(screen.queryByTestId("duplicate-remove-pair-1")).not.toBeInTheDocument();
      expect(screen.queryByTestId("duplicate-dismiss-pair-1")).not.toBeInTheDocument();
    });

    it("shows a finished removal under 'Removed in the last 24 hours'", async () => {
      mockList([pair({ status: "removed", removalOffered: false, preview: null, removal: removal("completed", { finishedAt: "2026-10-04T10:01:00Z" }) })]);
      renderPanel();

      expect(await screen.findByTestId("duplicate-removal-status-pair-1")).toHaveTextContent("Removed.");
      expect(within(screen.getByTestId("duplicates-group-removed")).getByRole("heading")).toHaveTextContent("Removed in the last 24 hours");
      expect(screen.queryByTestId("duplicate-remove-pair-1")).not.toBeInTheDocument();
    });

    it("says harmlessly that search-data cleanup failed after a removal", async () => {
      mockList([pair({ status: "removed", removalOffered: false, preview: null, removal: removal("embeddings_failed") })]);
      renderPanel();

      expect(await screen.findByTestId("duplicate-removal-status-pair-1")).toHaveTextContent("harmless");
    });

    it("shows a failed removal with its reason AND the actions again, so it can be retried", async () => {
      mockList([pair({ removal: removal("failed", { failureReason: "The manual corrections on this copy increased." }) })]);
      renderPanel();

      expect(await screen.findByTestId("duplicate-removal-status-pair-1")).toHaveTextContent("Removal failed: The manual corrections on this copy increased.");
      expect(screen.getByTestId("duplicates-group-awaiting")).toBeInTheDocument();
      expect(screen.getByTestId("duplicate-remove-pair-1")).toBeInTheDocument();
    });

    it("shows all three groups together, each with its own heading", async () => {
      mockList([
        pair({ id: "a", removal: removal("running") }),
        pair({ id: "b" }),
        pair({ id: "c", status: "removed", removalOffered: false, preview: null, removal: removal("completed") }),
      ]);
      renderPanel();

      await screen.findByTestId("duplicate-pair-a");
      expect(within(screen.getByTestId("duplicates-group-removing")).getByTestId("duplicate-pair-a")).toBeInTheDocument();
      expect(within(screen.getByTestId("duplicates-group-awaiting")).getByTestId("duplicate-pair-b")).toBeInTheDocument();
      expect(within(screen.getByTestId("duplicates-group-removed")).getByTestId("duplicate-pair-c")).toBeInTheDocument();
      expect(screen.queryByTestId("duplicates-none")).not.toBeInTheDocument();
    });

    it("polls every 3 seconds while a removal is in flight", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      mockList([pair({ removal: removal("running") })]);
      renderPanel();
      await screen.findByTestId("duplicate-pair-pair-1");
      const calls = vi.mocked(duplicatesApi.listPairs).mock.calls.length;

      await vi.advanceTimersByTimeAsync(3100);

      await waitFor(() => expect(vi.mocked(duplicatesApi.listPairs).mock.calls.length).toBeGreaterThan(calls));
    });

    it("does NOT poll when nothing is in flight", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      mockList([pair()]);
      renderPanel();
      await screen.findByTestId("duplicate-pair-pair-1");
      const calls = vi.mocked(duplicatesApi.listPairs).mock.calls.length;

      await vi.advanceTimersByTimeAsync(10000);

      expect(vi.mocked(duplicatesApi.listPairs).mock.calls.length).toBe(calls);
    });
  });

  describe("check again and paging", () => {
    it("asks for a re-check and says the worker will look shortly", async () => {
      mockList([]);
      const recheck = vi.spyOn(duplicatesApi, "requestRecheck").mockResolvedValue(scan({ recheckRequested: true }));
      renderPanel();
      const user = userEvent.setup();

      await user.click(await screen.findByTestId("duplicates-check-again"));

      await waitFor(() => expect(recheck).toHaveBeenCalled());
      expect(await screen.findByTestId("duplicates-recheck-requested")).toHaveTextContent("the worker will look shortly");
    });

    it("also shows a re-check that was already waiting", async () => {
      vi.spyOn(duplicatesApi, "getScanStatus").mockResolvedValue(scan({ recheckRequested: true }));
      mockList([]);
      renderPanel();

      expect(await screen.findByTestId("duplicates-recheck-requested")).toBeInTheDocument();
    });

    it("has no paging controls for a short list, and Previous/Next for a long one", async () => {
      mockList([pair()]);
      const { unmount } = renderPanel();
      await screen.findByTestId("duplicate-pair-pair-1");
      expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
      unmount();

      mockList([pair()], 45);
      renderPanel();
      await screen.findByTestId("duplicate-pair-pair-1");
      expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
    });
  });
});
