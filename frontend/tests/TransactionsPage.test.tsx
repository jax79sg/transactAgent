import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as accountsApi from "../src/api/accounts";
import * as categoriesApi from "../src/api/categories";
import * as transactionsApi from "../src/api/transactions";
import type { TransactionPage } from "../src/api/types";
import { AuthProvider } from "../src/context/AuthContext";
import { TransactionsPage } from "../src/pages/TransactionsPage";
import { accountsListFixture, FIXTURE_ACCOUNT_IDS } from "./balancesFixtures";

vi.mock("../src/api/transactions");
vi.mock("../src/api/categories");
vi.mock("../src/api/accounts");

// The page lists the owner's accounts in its Account filter; tests about something else get "none".
beforeEach(() => {
  vi.mocked(accountsApi.listAccounts).mockResolvedValue({ items: [] });
});

function pageOf(page: number, totalCount = 100, embeddingStatus: "pending" | "completed" = "pending"): TransactionPage {
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
        embeddingStatus,
      },
    ],
    page,
    pageSize: 50,
    totalCount,
    groups: null,
  };
}

function renderTransactionsPage(url = "/transactions") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[url]}>
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

describe("TransactionsPage column sorting (issue #10)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("clicking a sortable column header requests that column ascending first", async () => {
    const user = userEvent.setup();
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
    const listSpy = vi.spyOn(transactionsApi, "listTransactions").mockImplementation(async (filter) => {
      return pageOf(filter.page ?? 1);
    });
    renderTransactionsPage();

    await waitFor(() => expect(screen.getByTestId("sort-bank")).toBeInTheDocument());
    await user.click(screen.getByTestId("sort-bank"));

    await waitFor(() => {
      expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy: "bank", sortDir: "asc", page: 1 }));
    });
  });

  it("clicking an already-active sort column toggles its direction", async () => {
    const user = userEvent.setup();
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
    const listSpy = vi.spyOn(transactionsApi, "listTransactions").mockImplementation(async (filter) => {
      return pageOf(filter.page ?? 1);
    });
    renderTransactionsPage();

    await waitFor(() => expect(screen.getByTestId("sort-date")).toBeInTheDocument());
    await user.click(screen.getByTestId("sort-date"));
    await waitFor(() => {
      expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy: "date", sortDir: "asc" }));
    });

    await user.click(screen.getByTestId("sort-date"));
    await waitFor(() => {
      expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy: "date", sortDir: "desc" }));
    });
  });
});

describe("TransactionsPage sorts by description and converted amount (issue #23)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function setUpPage() {
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
    const listSpy = vi.spyOn(transactionsApi, "listTransactions").mockImplementation(async (filter) => {
      return pageOf(filter.page ?? 1);
    });
    renderTransactionsPage();
    return listSpy;
  }

  it.each([
    ["description", "sort-description"],
    ["converted", "sort-converted"],
  ])("clicking the %s header sorts by it, ascending first, then flips", async (sortBy, testId) => {
    const user = userEvent.setup();
    const listSpy = setUpPage();

    await waitFor(() => expect(screen.getByTestId(testId)).toBeInTheDocument());
    await user.click(screen.getByTestId(testId));
    await waitFor(() => {
      expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy, sortDir: "asc", page: 1 }));
    });
    expect(screen.getByTestId(testId)).toHaveAttribute("aria-sort", "ascending");

    await user.click(screen.getByTestId(testId));
    await waitFor(() => {
      expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy, sortDir: "desc" }));
    });
    expect(screen.getByTestId(testId)).toHaveAttribute("aria-sort", "descending");
  });

  it("makes only the clicked column the active one", async () => {
    const user = userEvent.setup();
    setUpPage();

    await waitFor(() => expect(screen.getByTestId("sort-description")).toBeInTheDocument());
    await user.click(screen.getByTestId("sort-description"));
    await waitFor(() => expect(screen.getByTestId("sort-description")).toHaveAttribute("aria-sort", "ascending"));

    for (const other of ["sort-date", "sort-bank", "sort-category", "sort-converted"]) {
      expect(screen.getByTestId(other)).toHaveAttribute("aria-sort", "none");
    }
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

describe("TransactionsPage embedding status badge", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders a pending-style badge when embeddingStatus is pending", async () => {
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(pageOf(1, 100, "pending"));
    renderTransactionsPage();

    await waitFor(() => expect(screen.getByTestId("embedding-status-badge")).toBeInTheDocument());
    expect(screen.getByTestId("embedding-status-badge")).toHaveAttribute("title", "Embedding: pending");
  });

  it("renders a completed-style badge when embeddingStatus is completed", async () => {
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(pageOf(1, 100, "completed"));
    renderTransactionsPage();

    await waitFor(() => expect(screen.getByTestId("embedding-status-badge")).toBeInTheDocument());
    expect(screen.getByTestId("embedding-status-badge")).toHaveAttribute("title", "Embedding: computed");
  });
});

describe("TransactionsPage accounts (issues #65-#70)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const { main, fresh, card } = FIXTURE_ACCOUNT_IDS;

  function withAccounts() {
    vi.mocked(accountsApi.listAccounts).mockResolvedValue(accountsListFixture());
    vi.spyOn(categoriesApi, "listCategories").mockResolvedValue([]);
    vi.spyOn(transactionsApi, "listBanks").mockResolvedValue([]);
  }

  it("lists every account in the Account filter, with its type and how many transactions it has, including one with none", async () => {
    withAccounts();
    vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(pageOf(1));
    renderTransactionsPage();

    expect(await screen.findByRole("option", { name: "Main · Savings / current · 4 transactions" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Trust USD · Savings / current · 1 transaction" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Visa Card · Credit card · no transactions" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Fresh · Savings / current · no transactions" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "All accounts" })).toBeInTheDocument();
  });

  it("choosing an account asks for that account's transactions", async () => {
    const user = userEvent.setup();
    withAccounts();
    const listSpy = vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(pageOf(1));
    renderTransactionsPage();
    await screen.findByRole("option", { name: "Main · Savings / current · 4 transactions" });

    await user.selectOptions(screen.getByTestId("account-filter-select"), main);

    await waitFor(() => expect(listSpy).toHaveBeenLastCalledWith(expect.objectContaining({ accountId: main })));
  });

  it("starts on the account in the address, so a link or a bookmark opens the same view", async () => {
    withAccounts();
    const listSpy = vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(pageOf(1));
    renderTransactionsPage(`/transactions?accountId=${card}`);

    await waitFor(() => expect(listSpy).toHaveBeenCalledWith(expect.objectContaining({ accountId: card })));
    await screen.findByRole("option", { name: "Visa Card · Credit card · no transactions" });
    expect(screen.getByTestId("account-filter-select")).toHaveValue(card);
  });

  it("names each transaction's account and its type, and shows a dash when it belongs to none", async () => {
    withAccounts();
    const page = pageOf(1);
    page.items.push({
      ...page.items[0],
      id: "txn-on-a-card",
      account: { id: card, name: "Visa Card", type: "credit_card" },
    });
    vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue(page);
    renderTransactionsPage();

    const onCard = await screen.findByTestId("txn-account-txn-on-a-card");
    expect(onCard).toHaveTextContent("Visa Card");
    expect(onCard).toHaveTextContent("Credit card");
    const unlinked = screen.getByTestId("txn-account-txn-page-1");
    expect(unlinked).toHaveTextContent("—");
    expect(unlinked).toHaveAttribute("title", "Not linked to an account");
  });

  it("says plainly that an account has no transactions, rather than just 'No matching transactions' (issue #69)", async () => {
    withAccounts();
    vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue({ items: [], page: 1, pageSize: 50, totalCount: 0, groups: null });
    renderTransactionsPage(`/transactions?accountId=${fresh}`);

    const message = await screen.findByTestId("account-has-no-transactions");
    expect(message).toHaveTextContent("“Fresh” has no transactions");
    expect(message).toHaveTextContent("none of its statements listed any");
  });

  it("keeps the ordinary empty message when an account that does have transactions matches nothing", async () => {
    withAccounts();
    vi.spyOn(transactionsApi, "listTransactions").mockResolvedValue({ items: [], page: 1, pageSize: 50, totalCount: 0, groups: null });
    renderTransactionsPage(`/transactions?accountId=${main}&textSearch=nothing`);

    expect(await screen.findByText("No matching transactions.")).toBeInTheDocument();
    expect(screen.queryByTestId("account-has-no-transactions")).not.toBeInTheDocument();
  });
});
