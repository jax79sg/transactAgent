import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as categoriesApi from "../src/api/categories";
import * as transactionsApi from "../src/api/transactions";
import type { TransactionPage } from "../src/api/types";
import { AuthProvider } from "../src/context/AuthContext";
import { TransactionsPage } from "../src/pages/TransactionsPage";

vi.mock("../src/api/transactions");
vi.mock("../src/api/categories");

function pageOf(page: number, totalCount = 100): TransactionPage {
  return {
    items: [
      {
        id: `txn-page-${page}`,
        transactionDate: "2026-01-15",
        description: `Transaction on page ${page}`,
        outFlow: "10.00",
        inFlow: null,
        currency: "SGD",
        bankName: "DBS",
        category: { id: "cat-1", name: "Household" },
        categorySource: "similarity",
        convertedAmountSgd: "10.00",
        conversionIsApproximate: false,
        conversionUnavailable: false,
        bankStatementId: "stmt-1",
      },
    ],
    page,
    pageSize: 50,
    totalCount,
    groups: null,
  };
}

function renderTransactionsPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/transactions"]}>
        <AuthProvider>
          <TransactionsPage />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TransactionsPage pagination", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("clicking Next actually requests and renders the next page (regression: page was being reset to 1)", async () => {
    const user = userEvent.setup();
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
    const listSpy = vi.spyOn(transactionsApi, "listTransactions").mockImplementation(async (filter) => {
      return pageOf(filter.page ?? 1);
    });
    renderTransactionsPage();

    await waitFor(() => {
      expect(screen.getByText("Transaction on page 1")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Next"));

    await waitFor(() => {
      expect(screen.getByText("Transaction on page 2")).toBeInTheDocument();
    });
    // The bug: updateFilter forced page back to 1 on every call, so this would have
    // been called with page: 1 again instead of page: 2.
    expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
  });

  it("clicking Previous moves back a page", async () => {
    const user = userEvent.setup();
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
    const listSpy = vi.spyOn(transactionsApi, "listTransactions").mockImplementation(async (filter) => {
      return pageOf(filter.page ?? 1);
    });
    renderTransactionsPage();

    await waitFor(() => expect(screen.getByText("Next")).toBeInTheDocument());
    await user.click(screen.getByText("Next"));
    await waitFor(() => expect(screen.getByText("Transaction on page 2")).toBeInTheDocument());

    await user.click(screen.getByText("Previous"));

    await waitFor(() => {
      expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }));
    });
  });

  it("changing a filter (text search) resets back to page 1", async () => {
    const user = userEvent.setup();
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
    const listSpy = vi.spyOn(transactionsApi, "listTransactions").mockImplementation(async (filter) => {
      return pageOf(filter.page ?? 1);
    });
    renderTransactionsPage();

    await waitFor(() => expect(screen.getByText("Next")).toBeInTheDocument());
    await user.click(screen.getByText("Next"));
    await waitFor(() => expect(screen.getByText("Transaction on page 2")).toBeInTheDocument());

    await user.type(screen.getByTestId("text-search-input"), "coffee");

    await waitFor(() => {
      expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, textSearch: expect.stringContaining("e") }));
    });
  });

  it("Next is disabled once the last page is reached", async () => {
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(pageOf(1, 1));
    renderTransactionsPage();

    await waitFor(() => expect(screen.getByText("Next")).toBeInTheDocument());
    expect(screen.getByText("Next")).toBeDisabled();
  });
});

describe("TransactionsPage bank and category filters", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("populates the bank filter options from listBanks", async () => {
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue(["DBS", "UOB"]);
    vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(pageOf(1));
    renderTransactionsPage();

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "DBS" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "UOB" })).toBeInTheDocument();
    });
  });

  it("populates the category filter options from listCategories", async () => {
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([
      { id: "cat-1", name: "Groceries", active: true, isReserved: false, transactionCount: 5 },
      { id: "cat-2", name: "Dining Out", active: true, isReserved: false, transactionCount: 2 },
    ]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(pageOf(1));
    renderTransactionsPage();

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Groceries" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Dining Out" })).toBeInTheDocument();
    });
  });

  it("selecting a bank filters the transaction list request", async () => {
    const user = userEvent.setup();
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue(["DBS", "UOB"]);
    const listSpy = vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(pageOf(1));
    renderTransactionsPage();

    await waitFor(() => expect(screen.getByRole("option", { name: "UOB" })).toBeInTheDocument());
    await user.selectOptions(screen.getByTestId("bank-filter-select"), "UOB");

    await waitFor(() => {
      expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ bank: "UOB", page: 1 }));
    });
  });

  it("selecting a category filters the transaction list request", async () => {
    const user = userEvent.setup();
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([
      { id: "cat-1", name: "Groceries", active: true, isReserved: false, transactionCount: 5 },
    ]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
    const listSpy = vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(pageOf(1));
    renderTransactionsPage();

    await waitFor(() => expect(screen.getByRole("option", { name: "Groceries" })).toBeInTheDocument());
    await user.selectOptions(screen.getByTestId("category-filter-select"), "Groceries");

    await waitFor(() => {
      expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ category: "Groceries", page: 1 }));
    });
  });
});

describe("TransactionsPage category list freshness (regression: newly-added category missing until reload)", () => {
  // Real bug: the app disables refetchOnWindowFocus globally, so a query that's
  // already mounted and cached (e.g. a long-lived open tab) never refetches on its
  // own once a category is added elsewhere (another tab, or earlier in the
  // session) -- staleTime: Infinity here simulates that "would otherwise never
  // refetch" condition precisely, isolating that the fix is the *explicit* refetch
  // fired at the point the user opens a picker, not some other incidental refetch.
  // Fixed by refetching right at the point the user opens a category/bank picker.
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function renderWithInfiniteStaleTime() {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/transactions"]}>
          <AuthProvider>
            <TransactionsPage />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("the per-transaction category editor picks up a category added after initial load", async () => {
    const user = userEvent.setup();
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(pageOf(1));
    const listCategoriesSpy = vi
      .spyOn(categoriesApi, "listCategories")
      .mockResolvedValueOnce([{ id: "cat-1", name: "Household", active: true, isReserved: false, transactionCount: 5 }])
      .mockResolvedValue([
        { id: "cat-1", name: "Household", active: true, isReserved: false, transactionCount: 5 },
        { id: "cat-2", name: "Transfer", active: true, isReserved: false, transactionCount: 0 },
      ]);
    renderWithInfiniteStaleTime();

    await waitFor(() => expect(screen.getByTestId("category-cell-txn-page-1")).toBeInTheDocument());
    expect(screen.queryByRole("option", { name: "Transfer" })).not.toBeInTheDocument();

    await user.click(screen.getByTestId("category-cell-txn-page-1"));

    await waitFor(() => expect(screen.getByRole("option", { name: "Transfer" })).toBeInTheDocument());
    expect(listCategoriesSpy.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("the bank filter picks up a bank added after initial load, refetched on focus", async () => {
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(pageOf(1));
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValueOnce(["DBS"]).mockResolvedValue(["DBS", "UOB"]);
    renderWithInfiniteStaleTime();

    await waitFor(() => expect(screen.getByTestId("bank-filter-select")).toBeInTheDocument());
    expect(screen.queryByRole("option", { name: "UOB" })).not.toBeInTheDocument();

    screen.getByTestId("bank-filter-select").focus();

    await waitFor(() => expect(screen.getByRole("option", { name: "UOB" })).toBeInTheDocument());
  });
});
