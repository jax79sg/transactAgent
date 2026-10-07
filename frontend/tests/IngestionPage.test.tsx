import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as ingestionApi from "../src/api/ingestion";
import type { RunFileDetail, RunStatusResponse } from "../src/api/types";
import { IngestionPage } from "../src/pages/IngestionPage";
import { label } from "./duplicatesFixtures";

vi.mock("../src/api/ingestion");

function runOf(overrides: Partial<RunStatusResponse> = {}): RunStatusResponse {
  return {
    runId: "run-1",
    status: "running",
    startedAt: "2026-08-05T00:00:00Z",
    completedAt: null,
    filesFoundCount: 10,
    filesProcessedCount: 3,
    filesSkippedCount: 0,
    filesFailedCount: 0,
    cancelRequestedAt: null,
    ...overrides,
  };
}

function renderIngestionPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <IngestionPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("IngestionPage cancellation", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows no Cancel button when there is no active run", async () => {
    vi.spyOn(ingestionApi, "listRunHistory").mockResolvedValue({
      items: [runOf({ status: "completed", filesProcessedCount: 10 })],
      page: 1,
      pageSize: 20,
      totalCount: 1,
    });

    renderIngestionPage();

    await waitFor(() => expect(screen.getByText("Run History")).toBeInTheDocument());
    expect(screen.queryByTestId("cancel-run-button")).not.toBeInTheDocument();
  });

  it("shows a Cancel button while a run is active", async () => {
    const active = runOf();
    vi.spyOn(ingestionApi, "listRunHistory").mockResolvedValue({
      items: [active],
      page: 1,
      pageSize: 20,
      totalCount: 1,
    });
    vi.spyOn(ingestionApi, "getRunStatus").mockResolvedValue(active);
    vi.spyOn(ingestionApi, "listRunLogs").mockResolvedValue([]);

    renderIngestionPage();

    await waitFor(() => expect(screen.getByTestId("cancel-run-button")).toBeInTheDocument());
    expect(screen.getByTestId("cancel-run-button")).toBeEnabled();
    expect(screen.getByText("Run status: running")).toBeInTheDocument();
  });

  it("clicking Cancel requests cancellation and shows a distinct Cancelling state", async () => {
    const user = userEvent.setup();
    const active = runOf();
    vi.spyOn(ingestionApi, "listRunHistory").mockResolvedValue({
      items: [active],
      page: 1,
      pageSize: 20,
      totalCount: 1,
    });
    vi.spyOn(ingestionApi, "getRunStatus").mockResolvedValue(active);
    vi.spyOn(ingestionApi, "listRunLogs").mockResolvedValue([]);
    const cancelSpy = vi
      .spyOn(ingestionApi, "cancelRun")
      .mockResolvedValue(runOf({ cancelRequestedAt: "2026-08-05T00:05:00Z" }));

    renderIngestionPage();

    await waitFor(() => expect(screen.getByTestId("cancel-run-button")).toBeInTheDocument());
    await user.click(screen.getByTestId("cancel-run-button"));

    expect(cancelSpy.mock.calls[0][0]).toBe("run-1");
    await waitFor(() => {
      expect(screen.getByText("Run status: Cancelling... (stops after the current file)")).toBeInTheDocument();
    });
    expect(screen.getByTestId("cancel-run-button")).toBeDisabled();
  });
});

function fileOf(overrides: Partial<RunFileDetail> = {}): RunFileDetail {
  return {
    id: "file-1",
    driveFileName: "JUN 2026_0828.pdf",
    outcome: "processed",
    failureReason: null,
    transactionsExtractedCount: 5,
    processedAt: "2026-08-05T00:01:00Z",
    duplicateComparisonId: null,
    matchedStatement: null,
    ...overrides,
  };
}

describe("IngestionPage probable-duplicate files (Epic 14)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  async function openRunWith(files: RunFileDetail[]) {
    const done = runOf({ status: "completed", filesProcessedCount: files.length });
    vi.spyOn(ingestionApi, "listRunHistory").mockResolvedValue({ items: [done], page: 1, pageSize: 20, totalCount: 1 });
    vi.spyOn(ingestionApi, "listRunFiles").mockResolvedValue(files);
    vi.spyOn(ingestionApi, "listRunLogs").mockResolvedValue([]);
    renderIngestionPage();
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("run-history-row-run-1"));
  }

  it("shows 'Probable duplicate of <statement>' as a link to the stored comparison", async () => {
    await openRunWith([
      fileOf({
        outcome: "skipped_probable_duplicate",
        duplicateComparisonId: "cmp-9",
        matchedStatement: label({ fileName: "JUN 2026_0728.pdf" }),
        transactionsExtractedCount: null,
      }),
    ]);

    const link = await screen.findByTestId("run-file-duplicate-link-file-1");
    expect(link).toHaveTextContent("Probable duplicate of JUN 2026_0728.pdf (UOB, 2 Jun to 30 Jun 2026)");
    expect(link).toHaveAttribute("href", "/duplicates/cmp-9");
    expect(screen.queryByText("skipped_probable_duplicate")).not.toBeInTheDocument(); // never the raw outcome code
  });

  it("falls back to plain words when the matched statement's label is missing", async () => {
    await openRunWith([
      fileOf({ outcome: "skipped_probable_duplicate", duplicateComparisonId: "cmp-9", matchedStatement: null }),
    ]);

    expect(await screen.findByTestId("run-file-duplicate-link-file-1")).toHaveTextContent(
      "Probable duplicate of a statement you already have",
    );
  });

  it("leaves every other outcome as it was, with no link", async () => {
    await openRunWith([
      fileOf({ id: "a", outcome: "processed" }),
      fileOf({ id: "b", outcome: "skipped_duplicate", driveFileName: "x.pdf" }),
      fileOf({ id: "c", outcome: "failed", driveFileName: "y.pdf", failureReason: "bad pdf" }),
    ]);

    await screen.findByText("skipped_duplicate");
    expect(screen.getByText("processed")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.queryByTestId(/run-file-duplicate-link-/)).not.toBeInTheDocument();
  });

  it("shows the raw outcome rather than a dead link if a skipped file somehow has no comparison to open", async () => {
    await openRunWith([fileOf({ outcome: "skipped_probable_duplicate", duplicateComparisonId: null })]);

    expect(await screen.findByText("skipped_probable_duplicate")).toBeInTheDocument();
    expect(screen.queryByTestId("run-file-duplicate-link-file-1")).not.toBeInTheDocument();
  });
});
