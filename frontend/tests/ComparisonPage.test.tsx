import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as duplicatesApi from "../src/api/duplicates";
import { ApiError } from "../src/api/client";
import type { DuplicateComparison } from "../src/api/types";
import { ComparisonPage } from "../src/pages/ComparisonPage";
import { comparison, label, row, side } from "./duplicatesFixtures";

vi.mock("../src/api/duplicates");

function renderPage(id = "cmp-1") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/duplicates/${id}`]}>
        <Routes>
          <Route path="/duplicates/:comparisonId" element={<ComparisonPage />} />
          <Route path="/review" element={<p>REVIEW PAGE</p>} />
          <Route path="/ingestion" element={<p>INGESTION PAGE</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

function mockComparison(c: DuplicateComparison) {
  return vi.spyOn(duplicatesApi, "getComparison").mockResolvedValue(c);
}

describe("ComparisonPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("the evidence", () => {
    it("shows the reason in words and the figures: both sizes, both periods, and how many matched", async () => {
      mockComparison(comparison());
      renderPage();

      expect(await screen.findByTestId("comparison-reason")).toHaveTextContent("5 of 5 transactions match (the smaller statement)");
      expect(screen.getByTestId("comparison-figures")).toHaveTextContent(
        "5 and 5 transactions (2 Jun to 30 Jun 2026 and 2 Jun to 30 Jun 2026); 5 matched.",
      );
    });

    it("fetches the comparison named in the address", async () => {
      const get = mockComparison(comparison({ id: "cmp-77" }));
      renderPage("cmp-77");

      await screen.findByTestId("comparison-reason");
      expect(get).toHaveBeenCalledWith("cmp-77");
    });

    it("shows both stored snapshots side by side, each row marked in words, with the direction on the amount", async () => {
      mockComparison(
        comparison({
          earlier: side({ rows: [row(1, { outFlow: "12.50", inFlow: null }), row(2, { marker: "only_on_this_one", outFlow: null, inFlow: "300.00" })] }),
          later: side({ label: label({ fileName: "JUN 2026_0828.pdf" }), rows: [row(1)] }),
        }),
      );
      renderPage();

      const earlier = await screen.findByTestId("comparison-earlier");
      const later = screen.getByTestId("comparison-later");
      expect(within(earlier).getByTestId("comparison-earlier-marker-1")).toHaveTextContent("Also on the other statement");
      expect(within(earlier).getByTestId("comparison-earlier-marker-2")).toHaveTextContent("Only on this one");
      expect(within(earlier).getByTestId("comparison-earlier-row-1")).toHaveTextContent("-12.50 SGD");
      expect(within(earlier).getByTestId("comparison-earlier-row-2")).toHaveTextContent("+300.00 SGD");
      expect(within(later).getAllByRole("row")).toHaveLength(2); // header + 1 snapshot row
    });

    it("also spells the marker out under each description, because on a phone the Match column is hidden and the marker is the evidence", async () => {
      mockComparison(comparison({ earlier: side({ rows: [row(1), row(2, { marker: "only_on_this_one" })] }) }));
      renderPage();

      const first = await screen.findByTestId("comparison-earlier-row-1");
      const second = screen.getByTestId("comparison-earlier-row-2");
      // twice in the row: the Match column (wide screens) and the line under the description (phones; `sm:hidden`)
      expect(within(first).getAllByText("Also on the other statement")).toHaveLength(2);
      expect(within(second).getAllByText("Only on this one")).toHaveLength(2);
      expect(within(first).getByTestId("comparison-earlier-marker-1").className).toContain("hidden");
    });

    it("says how many of each statement's transactions are shown, since only the largest are kept", async () => {
      mockComparison(comparison({ earlier: side({ label: label({ transactionCount: 42 }), rows: [row(1), row(2), row(3)] }) }));
      renderPage();

      expect(await screen.findByTestId("comparison-earlier")).toHaveTextContent("42 transactions; showing the 3 largest");
    });

    it("labels each side by a file name when it has one", async () => {
      mockComparison(comparison());
      renderPage();

      expect(await screen.findByTestId("comparison-earlier")).toHaveTextContent("JUN 2026_0728.pdf (UOB, 2 Jun to 30 Jun 2026)");
      expect(screen.getByTestId("comparison-later")).toHaveTextContent("JUN 2026_0828.pdf (UOB, 2 Jun to 30 Jun 2026)");
    });

    it("still labels a side whose file name was never recorded, by bank and period", async () => {
      mockComparison(comparison({ earlier: side({ label: label({ fileName: null }) }) }));
      renderPage();

      expect(await screen.findByTestId("comparison-earlier")).toHaveTextContent("UOB (2 Jun to 30 Jun 2026)");
    });
  });

  describe("naming the two sides", () => {
    it.each([
      ["later", "The statement it matches", "This file", "JUN 2026_0828.pdf"],
      ["earlier", "This file", "The statement it matches", "JUN 2026_0728.pdf"],
    ] as const)(
      "for a skipped file whose side is %s, the left panel is '%s' and the right is '%s', and the panel called 'This file' holds the skipped file",
      async (thisFileSide, left, right, skippedFileName) => {
        mockComparison(comparison({ thisFileSide }));
        renderPage();

        const earlier = await screen.findByTestId("comparison-earlier");
        const later = screen.getByTestId("comparison-later");
        expect(within(earlier).getByRole("heading")).toHaveTextContent(left);
        expect(within(later).getByRole("heading")).toHaveTextContent(right);
        const thisFilePanel = left === "This file" ? earlier : later;
        expect(thisFilePanel).toHaveTextContent(skippedFileName);
      },
    );

    it("for two stored statements, calls them earlier and later ingested", async () => {
      mockComparison(comparison({ state: "pair_pending", thisFileSide: null, canOverride: false, pairId: "pair-1", removalOffered: true }));
      renderPage();

      expect(await screen.findByRole("heading", { name: "Earlier ingested" })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Later ingested" })).toBeInTheDocument();
    });
  });

  describe("the state banner says what happened to the file", () => {
    it.each([
      ["skipped", "Skipped as a probable duplicate. It was not ingested."],
      ["removed", "Removed at your confirmation. The file is still in Google Drive."],
      ["ingest_at_next_run", "Will be ingested on the next ingestion run."],
      ["ingested_at_your_request", "Ingested at your request."],
      ["pair_dismissed", "You dismissed this pair as not a duplicate."],
      ["pair_superseded", "This pair is no longer current."],
    ] as const)("%s", async (state, text) => {
      mockComparison(comparison({ state, canOverride: false }));
      renderPage();

      expect(await screen.findByTestId("comparison-banner")).toHaveTextContent(text);
    });

    it("a pending pair where removal is offered points at the Review page", async () => {
      mockComparison(comparison({ state: "pair_pending", pairId: "pair-1", removalOffered: true, canOverride: false, thisFileSide: null }));
      renderPage();

      const banner = await screen.findByTestId("comparison-banner");
      expect(banner).toHaveTextContent("You can remove the duplicate from the Review page.");
      expect(within(banner).getByRole("link", { name: "Back to the Review page" })).toHaveAttribute("href", "/review");
    });

    it("a pending pair that is information-only says so, and does not promise a removal", async () => {
      mockComparison(comparison({ state: "pair_pending", pairId: "pair-1", removalOffered: false, canOverride: false, thisFileSide: null }));
      renderPage();

      const banner = await screen.findByTestId("comparison-banner");
      expect(banner).toHaveTextContent("Their sizes differ, so this is listed for information only.");
      expect(banner).not.toHaveTextContent("You can remove");
    });

    it("a file waiting for the next run links to Ingestion", async () => {
      mockComparison(comparison({ state: "ingest_at_next_run", canOverride: false }));
      renderPage();

      expect(await screen.findByRole("link", { name: "Go to Ingestion" })).toHaveAttribute("href", "/ingestion");
    });

    it("a skipped file's banner has no Review-page link (it belongs to no pair)", async () => {
      mockComparison(comparison());
      renderPage();

      await screen.findByTestId("comparison-banner");
      expect(screen.queryByRole("link", { name: "Back to the Review page" })).not.toBeInTheDocument();
    });
  });

  describe("overriding a skipped file", () => {
    it("is one click, because bringing back a merely skipped file is recoverable", async () => {
      mockComparison(comparison({ state: "skipped" }));
      const override = vi.spyOn(duplicatesApi, "overrideSkippedFile").mockResolvedValue({ comparisonId: "cmp-1", state: "ingest_at_next_run", note: null });
      renderPage();
      const user = userEvent.setup();

      await user.click(await screen.findByTestId("override-button"));

      await waitFor(() => expect(override).toHaveBeenCalledWith("cmp-1"));
      expect(screen.queryByTestId("override-warning")).not.toBeInTheDocument();
    });

    it("for a REMOVED copy takes a second, deliberate click, after a warning that its corrections are not restored", async () => {
      mockComparison(comparison({ state: "removed" }));
      const override = vi.spyOn(duplicatesApi, "overrideSkippedFile").mockResolvedValue({ comparisonId: "cmp-1", state: "ingest_at_next_run", note: null });
      renderPage();
      const user = userEvent.setup();

      await user.click(await screen.findByTestId("override-button"));

      expect(override).not.toHaveBeenCalled();
      expect(screen.getByTestId("override-warning")).toHaveTextContent("The manual corrections that sat on this copy are not restored.");
      expect(screen.queryByTestId("override-button")).not.toBeInTheDocument();

      await user.click(screen.getByTestId("override-confirm"));

      await waitFor(() => expect(override).toHaveBeenCalledTimes(1));
    });

    it("cancelling the second click changes nothing and brings the first button back", async () => {
      mockComparison(comparison({ state: "removed" }));
      const override = vi.spyOn(duplicatesApi, "overrideSkippedFile");
      renderPage();
      const user = userEvent.setup();

      await user.click(await screen.findByTestId("override-button"));
      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(override).not.toHaveBeenCalled();
      expect(screen.getByTestId("override-button")).toBeInTheDocument();
      expect(screen.queryByTestId("override-warning")).not.toBeInTheDocument();
    });

    it("refreshes the duplicates data after a success so the page and the badge catch up", async () => {
      mockComparison(comparison({ state: "skipped" }));
      vi.spyOn(duplicatesApi, "overrideSkippedFile").mockResolvedValue({ comparisonId: "cmp-1", state: "ingest_at_next_run", note: null });
      const { queryClient } = renderPage();
      const invalidate = vi.spyOn(queryClient, "invalidateQueries");
      const user = userEvent.setup();

      await user.click(await screen.findByTestId("override-button"));

      await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["duplicates"] }));
    });

    it("shows a failed override in plain words", async () => {
      mockComparison(comparison({ state: "skipped" }));
      vi.spyOn(duplicatesApi, "overrideSkippedFile").mockRejectedValue(new ApiError(409, { error: "not_a_skipped_file", message: "x" }));
      renderPage();
      const user = userEvent.setup();

      await user.click(await screen.findByTestId("override-button"));

      expect(await screen.findByTestId("override-error")).toBeInTheDocument();
      expect(screen.getByTestId("override-error").textContent).not.toBe("");
    });

    it.each(["ingest_at_next_run", "ingested_at_your_request", "pair_pending", "pair_dismissed"] as const)(
      "offers no override for %s",
      async (state) => {
        mockComparison(comparison({ state, canOverride: false, thisFileSide: state === "pair_pending" ? null : "later" }));
        renderPage();

        await screen.findByTestId("comparison-banner");
        expect(screen.queryByTestId("override-button")).not.toBeInTheDocument();
      },
    );

    it("trusts the server's canOverride, not the state alone", async () => {
      mockComparison(comparison({ state: "skipped", canOverride: false }));
      renderPage();

      await screen.findByTestId("comparison-banner");
      expect(screen.queryByTestId("override-button")).not.toBeInTheDocument();
    });
  });

  describe("when the comparison cannot be shown", () => {
    it("says it could not be found, with a Back button, when the server has no such comparison", async () => {
      vi.spyOn(duplicatesApi, "getComparison").mockRejectedValue(new ApiError(404, { error: "not_found", message: "x" }));
      renderPage("nope");

      expect(await screen.findByTestId("comparison-not-found")).toHaveTextContent("That comparison could not be found.");
      expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    });

    it("shows a loading line first", () => {
      vi.spyOn(duplicatesApi, "getComparison").mockReturnValue(new Promise(() => {}));
      renderPage();

      expect(screen.getByText("Loading...")).toBeInTheDocument();
    });
  });

  it("Back falls back to the Review page when there is no history to go back to", async () => {
    mockComparison(comparison());
    Object.defineProperty(window.history, "length", { value: 1, configurable: true });
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByTestId("comparison-back"));

    expect(await screen.findByText("REVIEW PAGE")).toBeInTheDocument();
  });
});
