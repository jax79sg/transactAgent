import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as backgroundActivityApi from "../src/api/backgroundActivity";
import * as duplicatesApi from "../src/api/duplicates";
import * as recategorizationApi from "../src/api/recategorization";
import * as recurringPaymentsApi from "../src/api/recurringPayments";
import { NavBar } from "../src/components/NavBar";
import { AuthProvider } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/context/ThemeContext";
import { appVersion } from "../src/version";

vi.mock("../src/api/recategorization");
vi.mock("../src/api/recurringPayments");
vi.mock("../src/api/backgroundActivity");
vi.mock("../src/api/duplicates");

const NO_ATTENTION_NEEDED = { dueSoonCount: 0, overdueCount: 0, pendingMatchCount: 0, newSuggestionCount: 0 };
const NO_ACTIVITY = { current: null, recent: [] };
const NO_PENDING_DUPLICATES = { pendingCount: 0 };

// Every NavBar render also asks for the probable-duplicate count; tests that are about something else get "none".
beforeEach(() => {
  vi.spyOn(duplicatesApi, "getPendingPairCount").mockResolvedValue(NO_PENDING_DUPLICATES);
});

function renderNavBar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MemoryRouter>
          <AuthProvider>
            <NavBar />
          </AuthProvider>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("NavBar pending review badge", () => {
  beforeEach(() => {
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue(NO_ATTENTION_NEEDED);
    vi.spyOn(backgroundActivityApi, "getActivitySummary").mockResolvedValue(NO_ACTIVITY);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows no badge when there are zero pending proposals", async () => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 0 });
    renderNavBar();

    await waitFor(() => {
      expect(recategorizationApi.getPendingCount).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("pending-review-badge")).not.toBeInTheDocument();
  });

  it("shows the pending count when proposals are waiting", async () => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 4 });
    renderNavBar();

    await waitFor(() => {
      expect(screen.getByTestId("pending-review-badge")).toHaveTextContent("4");
    });
  });

  it("includes a Review nav link", () => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 0 });
    renderNavBar();

    expect(screen.getByText("Review")).toBeInTheDocument();
  });
});

describe("NavBar recurring payments badge", () => {
  beforeEach(() => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 0 });
    vi.spyOn(backgroundActivityApi, "getActivitySummary").mockResolvedValue(NO_ACTIVITY);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows no badge when nothing needs attention", async () => {
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue(NO_ATTENTION_NEEDED);
    renderNavBar();

    await waitFor(() => {
      expect(recurringPaymentsApi.getRecurringPaymentsStatus).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("recurring-payments-badge")).not.toBeInTheDocument();
  });

  it("shows the combined due-soon + overdue + pending + suggestion count", async () => {
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue({
      dueSoonCount: 3, overdueCount: 1, pendingMatchCount: 2, newSuggestionCount: 1,
    });
    renderNavBar();

    await waitFor(() => {
      expect(screen.getByTestId("recurring-payments-badge")).toHaveTextContent("7"); // 3 + 1 + 2 + 1
    });
  });

  it("counts dueSoonCount toward the badge (issue #15 -- a due-soon payment must be visible without opening the Dashboard)", async () => {
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue({
      dueSoonCount: 5, overdueCount: 0, pendingMatchCount: 0, newSuggestionCount: 0,
    });
    renderNavBar();

    await waitFor(() => {
      expect(screen.getByTestId("recurring-payments-badge")).toHaveTextContent("5");
    });
  });
});

describe("NavBar activity indicator", () => {
  beforeEach(() => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 0 });
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue(NO_ATTENTION_NEEDED);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows a muted dot and no label when idle", async () => {
    vi.spyOn(backgroundActivityApi, "getActivitySummary").mockResolvedValue(NO_ACTIVITY);
    renderNavBar();

    await waitFor(() => {
      expect(backgroundActivityApi.getActivitySummary).toHaveBeenCalled();
    });
    expect(screen.getByTestId("activity-indicator")).toBeInTheDocument();
    expect(screen.queryByText(/in progress/)).not.toBeInTheDocument();
  });

  it("shows which job is running, not a generic label", async () => {
    vi.spyOn(backgroundActivityApi, "getActivitySummary").mockResolvedValue({
      current: { jobType: "recategorization_job", startedAt: "2026-08-18T09:00:00Z" },
      recent: [],
    });
    renderNavBar();

    await waitFor(() => {
      expect(screen.getByText("Recategorization scan in progress")).toBeInTheDocument();
    });
  });

  it("opens a panel with recent activity on click, even when idle", async () => {
    vi.spyOn(backgroundActivityApi, "getActivitySummary").mockResolvedValue({
      current: null,
      recent: [{ jobType: "ingestion_run", completedAt: "2026-08-18T08:00:00Z" }],
    });
    const user = userEvent.setup();
    renderNavBar();

    await waitFor(() => {
      expect(backgroundActivityApi.getActivitySummary).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("activity-panel")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("activity-indicator"));

    expect(screen.getByTestId("activity-panel")).toBeInTheDocument();
    expect(screen.getByText(/Ingestion run completed/)).toBeInTheDocument();
  });

  it("shows a no-recent-activity message when there's nothing to show", async () => {
    vi.spyOn(backgroundActivityApi, "getActivitySummary").mockResolvedValue(NO_ACTIVITY);
    const user = userEvent.setup();
    renderNavBar();

    await waitFor(() => {
      expect(backgroundActivityApi.getActivitySummary).toHaveBeenCalled();
    });
    await user.click(screen.getByTestId("activity-indicator"));

    expect(screen.getByText("No recent activity")).toBeInTheDocument();
  });
});

describe("NavBar theme toggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 0 });
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue(NO_ATTENTION_NEEDED);
    vi.spyOn(backgroundActivityApi, "getActivitySummary").mockResolvedValue(NO_ACTIVITY);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders and shows the current mode (light by default in tests)", () => {
    renderNavBar();

    expect(screen.getByTestId("theme-toggle")).toBeInTheDocument();
    expect(screen.getByTestId("theme-toggle-label")).toHaveTextContent("Light");
  });

  it("switches mode and updates the document's dark class when clicked", async () => {
    const user = userEvent.setup();
    renderNavBar();

    expect(document.documentElement.classList.contains("dark")).toBe(false);

    await user.click(screen.getByTestId("theme-toggle"));

    expect(screen.getByTestId("theme-toggle-label")).toHaveTextContent("Dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    await user.click(screen.getByTestId("theme-toggle"));

    expect(screen.getByTestId("theme-toggle-label")).toHaveTextContent("Light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("leaves the existing badges/activity indicator working alongside the toggle", async () => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 2 });
    renderNavBar();

    await waitFor(() => {
      expect(screen.getByTestId("pending-review-badge")).toHaveTextContent("2");
    });
    expect(screen.getByTestId("theme-toggle")).toBeInTheDocument();
  });
});

describe("NavBar pending duplicates badge", () => {
  beforeEach(() => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 0 });
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue(NO_ATTENTION_NEEDED);
    vi.spyOn(backgroundActivityApi, "getActivitySummary").mockResolvedValue(NO_ACTIVITY);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("is invisible when there are no pairs awaiting a decision", async () => {
    vi.spyOn(duplicatesApi, "getPendingPairCount").mockResolvedValue(NO_PENDING_DUPLICATES);
    renderNavBar();

    await waitFor(() => expect(duplicatesApi.getPendingPairCount).toHaveBeenCalled());
    expect(screen.queryByTestId("pending-duplicates-badge")).not.toBeInTheDocument();
  });

  it("shows the number of pairs awaiting a decision, on the Review link", async () => {
    vi.spyOn(duplicatesApi, "getPendingPairCount").mockResolvedValue({ pendingCount: 3 });
    renderNavBar();

    const badge = await screen.findByTestId("pending-duplicates-badge");
    expect(badge).toHaveTextContent("3");
    expect(screen.getByText("Review").closest("a")).toContainElement(badge);
  });

  it("is told apart from the recategorization badge: both can show at once, each with its own number", async () => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 4 });
    vi.spyOn(duplicatesApi, "getPendingPairCount").mockResolvedValue({ pendingCount: 2 });
    renderNavBar();

    await waitFor(() => expect(screen.getByTestId("pending-duplicates-badge")).toHaveTextContent("2"));
    expect(screen.getByTestId("pending-review-badge")).toHaveTextContent("4");
  });

  it("reads as words to a screen reader, not a bare number, and gets the plural right", async () => {
    const count = vi.spyOn(duplicatesApi, "getPendingPairCount").mockResolvedValue({ pendingCount: 1 });
    const { unmount } = renderNavBar();
    expect(await screen.findByTestId("pending-duplicates-badge")).toHaveAccessibleName("1 duplicate statement awaiting review");
    unmount();

    count.mockResolvedValue({ pendingCount: 5 });
    renderNavBar();
    expect(await screen.findByTestId("pending-duplicates-badge")).toHaveAccessibleName("5 duplicate statements awaiting review");
  });

  it("does not disturb the existing recategorization badge when there are no duplicates", async () => {
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 6 });
    vi.spyOn(duplicatesApi, "getPendingPairCount").mockResolvedValue(NO_PENDING_DUPLICATES);
    renderNavBar();

    await waitFor(() => expect(screen.getByTestId("pending-review-badge")).toHaveTextContent("6"));
    expect(screen.queryByTestId("pending-duplicates-badge")).not.toBeInTheDocument();
  });
});


describe("NavBar links", () => {
  beforeEach(() => {
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue(NO_ATTENTION_NEEDED);
    vi.spyOn(backgroundActivityApi, "getActivitySummary").mockResolvedValue(NO_ACTIVITY);
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 0 });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("has a Costs link to the costs page, between Review and Settings (issue #28)", async () => {
    renderNavBar();

    const labels = screen.getAllByRole("link").map((link) => link.textContent);
    expect(labels.indexOf("Costs")).toBe(labels.indexOf("Review") + 1);
    expect(labels.indexOf("Settings")).toBe(labels.indexOf("Costs") + 1);
    expect(screen.getByRole("link", { name: "Costs" })).toHaveAttribute("href", "/costs");
  });
});

describe("NavBar release label (issue #27)", () => {
  beforeEach(() => {
    vi.spyOn(recurringPaymentsApi, "getRecurringPaymentsStatus").mockResolvedValue(NO_ATTENTION_NEEDED);
    vi.spyOn(backgroundActivityApi, "getActivitySummary").mockResolvedValue(NO_ACTIVITY);
    vi.spyOn(recategorizationApi, "getPendingCount").mockResolvedValue({ pendingCount: 0 });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("always shows the release, linking to the About card on Settings", () => {
    renderNavBar();

    const label = screen.getByTestId("app-version");
    expect(label).toHaveTextContent(`v${appVersion}`);
    expect(label).toHaveAttribute("href", "/settings#about");
  });
});
