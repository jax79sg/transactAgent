import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as ingestionApi from "../src/api/ingestion";
import { RunLiveLogs } from "../src/pages/IngestionPage";
import type { RunLogLine } from "../src/api/types";

// waitFor() and fake timers deadlock each other -- waitFor's own internal retry loop
// is timer-driven, so once vi.useFakeTimers() is active it never actually ticks unless
// timers are advanced from inside the same synchronous call, which `await waitFor(...)`
// can't do. Every assertion below instead explicitly advances fake time (flushing
// pending microtasks too, via advanceTimersByTimeAsync) inside act(), then asserts
// synchronously.
vi.mock("../src/api/ingestion");

function line(id: number, message: string): RunLogLine {
  return { id, loggedAt: new Date().toISOString(), level: "INFO", loggerName: "ingestion_worker.test", message };
}

async function flush(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("RunLiveLogs", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("shows a placeholder before any lines have arrived", async () => {
    vi.spyOn(ingestionApi, "listRunLogs").mockResolvedValue([]);
    render(<RunLiveLogs runId="run-1" isActive={true} />);

    await flush();

    expect(screen.getByText("No log output yet.")).toBeInTheDocument();
  });

  it("renders lines from the initial fetch and accumulates new ones on later polls", async () => {
    const spy = vi
      .spyOn(ingestionApi, "listRunLogs")
      .mockResolvedValueOnce([line(1, "Starting run"), line(2, "Found 2 files")])
      .mockResolvedValueOnce([line(3, "Processing file 1/2")]);

    render(<RunLiveLogs runId="run-1" isActive={true} />);
    await flush();

    expect(screen.getByTestId("run-live-logs")).toHaveTextContent("Starting run");
    expect(screen.getByTestId("run-live-logs")).toHaveTextContent("Found 2 files");

    await flush(2000);

    expect(screen.getByTestId("run-live-logs")).toHaveTextContent("Processing file 1/2");
    // earlier lines must still be present -- polling appends, it doesn't replace
    expect(screen.getByTestId("run-live-logs")).toHaveTextContent("Starting run");
    // the second poll must ask for lines after the last id it already has (2), not
    // refetch from the start
    expect(spy).toHaveBeenNthCalledWith(2, "run-1", 2);
  });

  it("stops polling once the run is no longer active", async () => {
    const spy = vi.spyOn(ingestionApi, "listRunLogs").mockResolvedValue([line(1, "Run complete")]);

    render(<RunLiveLogs runId="run-1" isActive={false} />);
    await flush();
    expect(spy).toHaveBeenCalledTimes(1);

    await flush(10000);
    expect(spy).toHaveBeenCalledTimes(1); // no interval was ever set
  });

  it("resets accumulated lines when switching to a different run", async () => {
    vi.spyOn(ingestionApi, "listRunLogs").mockImplementation(async (runId) =>
      runId === "run-1" ? [line(1, "Run 1 log")] : [line(1, "Run 2 log")],
    );

    const { rerender } = render(<RunLiveLogs runId="run-1" isActive={false} />);
    await flush();
    expect(screen.getByTestId("run-live-logs")).toHaveTextContent("Run 1 log");

    rerender(<RunLiveLogs runId="run-2" isActive={false} />);
    await flush();

    expect(screen.getByTestId("run-live-logs")).toHaveTextContent("Run 2 log");
    expect(screen.getByTestId("run-live-logs")).not.toHaveTextContent("Run 1 log");
  });
});
