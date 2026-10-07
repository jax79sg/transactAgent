import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as categoriesApi from "../src/api/categories";
import * as driveConnectApi from "../src/api/driveConnect";
import * as settingsApi from "../src/api/settings";
import * as versionApi from "../src/api/version";
import type { SettingDTO } from "../src/api/types";
import { RELEASES_URL, guideUrlFor } from "../src/lib/guideLinks";
import { SettingsPage } from "../src/pages/SettingsPage";
import { appVersion } from "../src/version";

vi.mock("../src/api/categories");
vi.mock("../src/api/driveConnect");
vi.mock("../src/api/settings");
vi.mock("../src/api/version");

const SIMILARITY_THRESHOLD_SETTING: SettingDTO = {
  name: "similarity_threshold",
  value: "85.0",
  isOverridden: false,
  owningServices: ["ingestion-worker"],
  classification: "standard",
  category: "Matching & Categorization",
  description: "Fuzzy-text match score (0-100) a candidate transaction must reach to be treated as the same payee during categorization.",
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
  category: "Embedding & Semantic Matching",
  description: "A wrong value here disables embedding matching with no error shown.",
  type: "string",
};

const DUPLICATE_SWITCH_SETTING: SettingDTO = {
  name: "duplicate_detection_enabled",
  value: "false",
  isOverridden: false,
  owningServices: ["ingestion-worker", "api-service"],
  classification: "standard",
  category: "Duplicate Statements",
  description: "Whether the same statement arriving as a different file is detected.",
  type: "enum",
  allowedValues: ["false", "true"],
};

function renderSettingsPage(
  settings: SettingDTO[] = [SIMILARITY_THRESHOLD_SETTING, EMBEDDING_BASE_URL_SETTING],
  initialEntry = "/settings",
  serverVersion: () => Promise<{ version: string }> = () => Promise.resolve({ version: appVersion }),
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
  // Default, always-on mock -- ApplicationSettingsSection's list query runs
  // unconditionally on every SettingsPage render, same precedent as
  // ReviewPage.test.tsx's beforeEach default for DisagreementTable's always-on query.
  vi.spyOn(settingsApi, "listSettings").mockResolvedValue(settings);
  vi.spyOn(settingsApi, "listSettingHistory").mockResolvedValue([]);
  vi.spyOn(versionApi, "getServerVersion").mockImplementation(serverVersion);
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
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

  it("groups settings by category, matching .env.example's own organization", async () => {
    vi.spyOn(driveConnectApi, "getDriveStatus").mockResolvedValue({ connected: false });
    renderSettingsPage();

    await waitFor(() => {
      expect(screen.getByTestId("setting-row-similarity_threshold")).toBeInTheDocument();
    });
    expect(screen.getByTestId("setting-row-embedding_base_url")).toBeInTheDocument();
    expect(screen.getByTestId("setting-category-Matching & Categorization")).toBeInTheDocument();
    expect(screen.getByTestId("setting-category-Embedding & Semantic Matching")).toBeInTheDocument();
    // The Advanced setting's real, specific description (from the API, not a
    // hardcoded frontend copy) is shown, not a generic warning.
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

describe("SettingsPage enumerated settings (Epic 14 on/off switch)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const SETTINGS = [SIMILARITY_THRESHOLD_SETTING, DUPLICATE_SWITCH_SETTING];

  it("shows the switch under its own 'Duplicate Statements' category, as false/true in lowercase", async () => {
    vi.spyOn(driveConnectApi, "getDriveStatus").mockResolvedValue({ connected: false });
    renderSettingsPage(SETTINGS);

    await waitFor(() => expect(screen.getByTestId("setting-row-duplicate_detection_enabled")).toBeInTheDocument());
    expect(screen.getByTestId("setting-category-Duplicate Statements")).toBeInTheDocument();
    expect(screen.getByTestId("setting-row-duplicate_detection_enabled")).toHaveTextContent("false");
  });

  it("edits an enumerated setting with a dropdown of exactly its allowed values", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    vi.spyOn(driveConnectApi, "getDriveStatus").mockResolvedValue({ connected: false });
    renderSettingsPage(SETTINGS);
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByTestId("setting-row-duplicate_detection_enabled")).toBeInTheDocument());
    await user.click(within(screen.getByTestId("setting-row-duplicate_detection_enabled")).getByText("Edit"));

    const control = screen.getByTestId("setting-input-duplicate_detection_enabled");
    expect(control.tagName).toBe("SELECT");
    expect(within(control).getAllByRole("option").map((o) => o.textContent)).toEqual(["false", "true"]);
    expect(control).toHaveValue("false"); // starts at the current value
  });

  it("still edits a numeric setting with a text box", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    vi.spyOn(driveConnectApi, "getDriveStatus").mockResolvedValue({ connected: false });
    renderSettingsPage(SETTINGS);
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByTestId("setting-row-similarity_threshold")).toBeInTheDocument());
    await user.click(within(screen.getByTestId("setting-row-similarity_threshold")).getByText("Edit"));

    expect(screen.getByTestId("setting-input-similarity_threshold").tagName).toBe("INPUT");
  });

  it("chooses a value from the dropdown, confirms, and saves exactly that string", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    vi.spyOn(driveConnectApi, "getDriveStatus").mockResolvedValue({ connected: false });
    vi.spyOn(settingsApi, "updateSetting").mockResolvedValue({
      setting: { ...DUPLICATE_SWITCH_SETTING, value: "true", isOverridden: true },
      restartGuidance: [{ owningService: "ingestion-worker", restartCommand: "docker restart transactagent-worker" }],
    });
    renderSettingsPage(SETTINGS);
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByTestId("setting-row-duplicate_detection_enabled")).toBeInTheDocument());
    await user.click(within(screen.getByTestId("setting-row-duplicate_detection_enabled")).getByText("Edit"));
    await user.selectOptions(screen.getByTestId("setting-input-duplicate_detection_enabled"), "true");
    await user.click(screen.getByText("Save"));

    expect(settingsApi.updateSetting).not.toHaveBeenCalled(); // the confirmation comes first, as for every setting
    await user.click(screen.getByTestId("confirm-setting-change"));

    await waitFor(() => expect(settingsApi.updateSetting).toHaveBeenCalledWith("duplicate_detection_enabled", "true"));
    await waitFor(() => expect(screen.getByTestId("restart-command")).toHaveTextContent("docker restart transactagent-worker"));
  });
});


describe("SettingsPage About card (issue #27)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the release of the interface and of the server", async () => {
    renderSettingsPage();

    expect(screen.getByTestId("about-interface-version")).toHaveTextContent(`v${appVersion}`);
    await waitFor(() => expect(screen.getByTestId("about-server-version")).toHaveTextContent(`v${appVersion}`));
  });

  it("says nothing about a mismatch when the two agree", async () => {
    renderSettingsPage();
    await waitFor(() => expect(screen.getByTestId("about-server-version")).toHaveTextContent(`v${appVersion}`));

    expect(screen.queryByTestId("about-version-mismatch")).not.toBeInTheDocument();
  });

  it("warns, naming both releases, when the server is on a different one", async () => {
    renderSettingsPage(undefined, "/settings", () => Promise.resolve({ version: "9.9.9" }));

    const warning = await screen.findByTestId("about-version-mismatch");
    expect(warning).toHaveTextContent(`interface (v${appVersion})`);
    expect(warning).toHaveTextContent("server (v9.9.9)");
    expect(screen.getByTestId("about-server-version")).toHaveTextContent("v9.9.9");
  });

  it("says the server's release is unavailable when it cannot be read, without crying mismatch", async () => {
    renderSettingsPage(undefined, "/settings", () => Promise.reject(new Error("down")));

    await waitFor(() => expect(screen.getByTestId("about-server-version")).toHaveTextContent("unavailable"));
    expect(screen.queryByTestId("about-version-mismatch")).not.toBeInTheDocument();
  });

  it("says it is checking while the server has not yet answered, without crying mismatch", async () => {
    renderSettingsPage(undefined, "/settings", () => new Promise(() => {}));

    expect(screen.getByTestId("about-server-version")).toHaveTextContent("checking...");
    expect(screen.queryByTestId("about-version-mismatch")).not.toBeInTheDocument();
  });

  it("links to this release's own guide and to the list of all releases, in a new tab", async () => {
    renderSettingsPage();

    const guide = screen.getByTestId("about-guide-link");
    expect(guide).toHaveAttribute("href", guideUrlFor(appVersion));
    expect(guide).toHaveTextContent(`User guide for v${appVersion}`);
    expect(guide).toHaveAttribute("target", "_blank");
    expect(guide).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByTestId("about-releases-link")).toHaveAttribute("href", RELEASES_URL);
  });

  it("scrolls into view when reached from the nav bar's version label", async () => {
    const scroll = vi.spyOn(Element.prototype, "scrollIntoView");
    renderSettingsPage(undefined, "/settings#about");

    await waitFor(() => expect(scroll).toHaveBeenCalled());
    expect(scroll.mock.contexts[0]).toBe(screen.getByTestId("about-card"));
  });

  it("does not scroll when Settings is opened normally", async () => {
    const scroll = vi.spyOn(Element.prototype, "scrollIntoView");
    renderSettingsPage();
    await waitFor(() => expect(screen.getByTestId("about-server-version")).toHaveTextContent(`v${appVersion}`));

    expect(scroll).not.toHaveBeenCalled();
  });
});
