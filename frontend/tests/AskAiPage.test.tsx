import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as aiAssistantApi from "../src/api/aiAssistant";
import { ApiError } from "../src/api/client";
import { AskAiPage } from "../src/pages/AskAiPage";

vi.mock("../src/api/aiAssistant");

function renderAskAiPage(initialEntry = "/ask-ai") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AskAiPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AskAiPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("pre-fills the question and date range from URL search params (the per-transaction shortcut)", () => {
    renderAskAiPage("/ask-ai?question=What+is+this%3F&dateFrom=2026-01-01&dateTo=2026-02-01");

    expect(screen.getByTestId("ask-ai-question-input")).toHaveValue("What is this?");
    expect(screen.getByTestId("ask-ai-date-from")).toHaveValue("2026-01-01");
    expect(screen.getByTestId("ask-ai-date-to")).toHaveValue("2026-02-01");
  });

  it("submits the question with the date range and shows the grounded answer", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(aiAssistantApi, "askAi").mockResolvedValue({
      answer: "This looks like a transfer to your credit card, based on the matching amount on Jan 16.",
      transactionsConsidered: 42,
      truncated: false,
    });
    renderAskAiPage("/ask-ai?dateFrom=2026-01-01&dateTo=2026-02-01");

    await user.type(screen.getByTestId("ask-ai-question-input"), "Is this a transfer?");
    await user.click(screen.getByTestId("ask-ai-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("ask-ai-answer")).toHaveTextContent("This looks like a transfer");
    });
    expect(screen.getByTestId("ask-ai-answer")).toHaveTextContent("Based on 42 transactions");
    expect(spy).toHaveBeenCalledWith({ question: "Is this a transfer?", dateFrom: "2026-01-01", dateTo: "2026-02-01" });
  });

  it("sends useAllTransactions and omits the date range when the checkbox is checked", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(aiAssistantApi, "askAi").mockResolvedValue({
      answer: "Answer",
      transactionsConsidered: 2000,
      truncated: true,
    });
    renderAskAiPage();

    await user.type(screen.getByTestId("ask-ai-question-input"), "Anything unusual ever?");
    await user.click(screen.getByTestId("ask-ai-use-all-transactions"));
    await user.click(screen.getByTestId("ask-ai-submit"));

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith({ question: "Anything unusual ever?", useAllTransactions: true });
    });
    await waitFor(() => {
      expect(screen.getByTestId("ask-ai-answer")).toHaveTextContent(
        "some older matches were left out to keep the request a reasonable size",
      );
    });
  });

  it("shows a friendly message when there are no transactions in scope", async () => {
    const user = userEvent.setup();
    vi.spyOn(aiAssistantApi, "askAi").mockRejectedValue(
      new ApiError(400, { error: "no_transactions_in_scope", message: "No transactions found in the selected scope" }),
    );
    renderAskAiPage("/ask-ai?dateFrom=2020-01-01&dateTo=2020-02-01");

    await user.type(screen.getByTestId("ask-ai-question-input"), "Anything here?");
    await user.click(screen.getByTestId("ask-ai-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("ask-ai-error")).toHaveTextContent("No transactions found in that date range");
    });
  });

  it("disables the submit button until a question is entered", () => {
    renderAskAiPage();
    expect(screen.getByTestId("ask-ai-submit")).toBeDisabled();
  });
});
