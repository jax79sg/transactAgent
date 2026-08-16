import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as categoriesApi from "../src/api/categories";
import * as driveConnectApi from "../src/api/driveConnect";
import * as settingsApi from "../src/api/settings";
import type { SettingDTO } from "../src/api/types";
import { SettingsPage } from "../src/pages/SettingsPage";

vi.mock("../src/api/categories");
vi.mock("../src/api/driveConnect");
vi.mock("../src/api/settings");

const SIMILARITY_THRESHOLD_SETTING: SettingDTO = {
  name: "similarity_threshold",
  value: "85.0",
  isOverridden: false,
  owningServices: ["ingestion-worker"],
  classification: "standard",
  type: "float",
  min: 0,
  max: 100,
};

const EMBEDDING_BASE_URL_SETTING: SettingDTO = {
  name: "embedding_base_url",
  value: "",
  isOverridden: false,
  owningServices: ["ingestion-worker"],
  classification: "advanced",
  type: "string",
};

function renderSettingsPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
  // Default, always-on mock -- ApplicationSettingsSection's list query runs
  // unconditionally on every SettingsPage render, same precedent as
  // ReviewPage.test.tsx's beforeEach default for DisagreementTable's always-on query.
  vi.spyOn(settingsApi, "listSettings").mockResolvedValue([SIMILARITY_THRESHOLD_SETTING, EMBEDDING_BASE_URL_SETTING]);
  vi.spyOn(settingsApi, "listSettingHistory").mockResolvedValue([]);
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

describe("SettingsPage Application Settings section", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("groups settings into Standard and Advanced sections", async () => {
    vi.spyOn(driveConnectApi, "getDriveStatus").mockResolvedValue({ connected: false });
    renderSettingsPage();

    await waitFor(() => {
      expect(screen.getByTestId("setting-row-similarity_threshold")).toBeInTheDocument();
    });
    expect(screen.getByTestId("setting-row-embedding_base_url")).toBeInTheDocument();
    expect(screen.getByText("Advanced")).toBeInTheDocument();
    // The Advanced setting's specific risk note is shown, not a generic warning.
    expect(screen.getByText(/disables embedding matching with no error shown/)).toBeInTheDocument();
  });

  it("edit -> confirm -> save calls updateSetting and shows restart guidance", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    vi.spyOn(driveConnectApi, "getDriveStatus").mockResolvedValue({ connected: false });
    vi.spyOn(settingsApi, "updateSetting").mockResolvedValue({
      setting: { ...SIMILARITY_THRESHOLD_SETTING, value: "90.0", isOverridden: true },
      restartGuidance: [{ owningService: "ingestion-worker", restartCommand: "docker restart transactagent-worker" }],
    });
    renderSettingsPage();
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByTestId("setting-row-similarity_threshold")).toBeInTheDocument());
    await user.click(screen.getAllByText("Edit")[0]);

    const input = screen.getByTestId("setting-input-similarity_threshold");
    await user.clear(input);
    await user.type(input, "90.0");
    await user.click(screen.getByText("Save"));

    // Confirmation dialog, not an immediate write (FR-CAS-10) -- distinct from
    // CategoryManagement's lower-friction inline save.
    expect(settingsApi.updateSetting).not.toHaveBeenCalled();
    expect(screen.getByTestId("confirm-setting-change")).toBeInTheDocument();

    await user.click(screen.getByTestId("confirm-setting-change"));

    await waitFor(() => expect(settingsApi.updateSetting).toHaveBeenCalledWith("similarity_threshold", "90.0"));
    await waitFor(() => expect(screen.getByTestId("restart-command")).toHaveTextContent("docker restart transactagent-worker"));
  });

  it("shows a busy message instead of the restart command when the worker is busy", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    vi.spyOn(driveConnectApi, "getDriveStatus").mockResolvedValue({ connected: false });
    vi.spyOn(settingsApi, "updateSetting").mockResolvedValue({
      setting: { ...SIMILARITY_THRESHOLD_SETTING, value: "90.0", isOverridden: true },
      restartGuidance: [{ owningService: "ingestion-worker", restartCommand: "docker restart transactagent-worker", workerBusy: true }],
    });
    vi.spyOn(settingsApi, "getRestartGuidance").mockResolvedValue([
      { owningService: "ingestion-worker", restartCommand: "docker restart transactagent-worker", workerBusy: true },
    ]);
    renderSettingsPage();
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByTestId("setting-row-similarity_threshold")).toBeInTheDocument());
    await user.click(screen.getAllByText("Edit")[0]);
    await user.click(screen.getByText("Save"));
    await user.click(screen.getByTestId("confirm-setting-change"));

    await waitFor(() => {
      expect(screen.getByText(/worker is currently processing/)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("restart-command")).not.toBeInTheDocument();
  });

  it("shows an inline validation error without closing the edit form on 400", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const { ApiError } = await import("../src/api/client");
    vi.spyOn(driveConnectApi, "getDriveStatus").mockResolvedValue({ connected: false });
    vi.spyOn(settingsApi, "updateSetting").mockRejectedValue(
      new ApiError(400, { error: "invalid_setting_value", message: "Invalid value for 'similarity_threshold': must be at most 100.0" }),
    );
    renderSettingsPage();
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByTestId("setting-row-similarity_threshold")).toBeInTheDocument());
    await user.click(screen.getAllByText("Edit")[0]);
    await user.click(screen.getByText("Save"));
    await user.click(screen.getByTestId("confirm-setting-change"));

    await waitFor(() => {
      expect(screen.getByText(/must be at most 100.0/)).toBeInTheDocument();
    });
  });

  it("expands to show change history on demand", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    vi.spyOn(driveConnectApi, "getDriveStatus").mockResolvedValue({ connected: false });
    vi.spyOn(settingsApi, "listSettingHistory").mockResolvedValue([
      {
        id: "h1",
        settingName: "similarity_threshold",
        owningService: "ingestion-worker",
        previousValue: "85.0",
        newValue: "90.0",
        changedAt: "2026-08-16T05:00:00Z",
      },
    ]);
    renderSettingsPage();
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByTestId("setting-row-similarity_threshold")).toBeInTheDocument());
    expect(screen.queryByText(/85.0.*90.0/)).not.toBeInTheDocument();

    await user.click(screen.getByTestId("toggle-setting-history"));

    await waitFor(() => {
      expect(screen.getByText(/85.0/)).toBeInTheDocument();
    });
  });
});
