import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as ingestionApi from "../src/api/ingestion";
import type { RunStatusResponse } from "../src/api/types";
import { IngestionPage } from "../src/pages/IngestionPage";

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
      <IngestionPage />
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
