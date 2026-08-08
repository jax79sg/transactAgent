import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as categoriesApi from "../src/api/categories";
import * as driveConnectApi from "../src/api/driveConnect";
import { SettingsPage } from "../src/pages/SettingsPage";

vi.mock("../src/api/categories");
vi.mock("../src/api/driveConnect");

function renderSettingsPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SettingsPage Drive connection card", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows 'Connect Google Drive' and the button when not yet connected", async () => {
    vi.spyOn(driveConnectApi, "getDriveStatus").mockResolvedValue({ connected: false });
    renderSettingsPage();

    await waitFor(() => {
      expect(screen.getByText("Not connected")).toBeInTheDocument();
    });
    expect(screen.getByTestId("connect-drive-button")).toHaveTextContent("Connect Google Drive");
  });

  it("still shows the button, relabeled 'Reconnect', when already connected", async () => {
    // Regression coverage: a previously-connected credential (e.g. one granted under
    // an older, narrower OAuth scope) must still offer a way back into the connect
    // flow -- caught live when a scope change left no UI path to re-grant consent
    // (aidlc-docs/audit.md 2026-08-08).
    vi.spyOn(driveConnectApi, "getDriveStatus").mockResolvedValue({ connected: true });
    renderSettingsPage();

    await waitFor(() => {
      expect(screen.getByText("Connected")).toBeInTheDocument();
    });
    expect(screen.getByTestId("connect-drive-button")).toHaveTextContent("Reconnect Google Drive");
  });
});
