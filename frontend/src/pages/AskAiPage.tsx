import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { askAi } from "../api/aiAssistant";
import { ApiError } from "../api/client";

function defaultDateFrom(): string {
  const d = new Date();
  d.setMonth(d.getMonth() - 3);
  return d.toISOString().slice(0, 10);
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.body.error === "no_transactions_in_scope") {
      return "No transactions found in that date range — try widening it, or check “Use all transactions”.";
    }
    if (err.body.error === "invalid_date_range") {
      return "Check your date range — the start date must be before the end date.";
    }
    if (err.body.error === "ai_service_unavailable") {
      return "The AI assistant is temporarily unavailable. Try asking again in a moment.";
    }
    return err.body.message;
  }
  return "Something went wrong asking that question. Try again.";
}

export function AskAiPage() {
  const [searchParams] = useSearchParams();
  const [question, setQuestion] = useState(searchParams.get("question") ?? "");
  const [dateFrom, setDateFrom] = useState(searchParams.get("dateFrom") ?? defaultDateFrom());
  const [dateTo, setDateTo] = useState(searchParams.get("dateTo") ?? todayIso());
  const [useAllTransactions, setUseAllTransactions] = useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      askAi(
        useAllTransactions
          ? { question, useAllTransactions: true }
          : { question, dateFrom, dateTo },
      ),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (question.trim()) mutation.mutate();
  }

  return (
    <div className="max-w-2xl">
      <h1 className="mb-1 text-xl font-semibold">Ask AI</h1>
      <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
        Ask a question about your transactions in plain language. The answer is grounded in your own
        transaction data — not general financial advice.
      </p>

      <form onSubmit={handleSubmit} className="space-y-3">
        <textarea
          data-testid="ask-ai-question-input"
          className="w-full rounded border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          rows={3}
          placeholder='e.g. "Is the $33,000 outflow on 15 Jan likely a transfer to my credit account?"'
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />

        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2">
            From
            <input
              type="date"
              data-testid="ask-ai-date-from"
              value={dateFrom}
              disabled={useAllTransactions}
              onChange={(e) => setDateFrom(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            />
          </label>
          <label className="flex items-center gap-2">
            To
            <input
              type="date"
              data-testid="ask-ai-date-to"
              value={dateTo}
              disabled={useAllTransactions}
              onChange={(e) => setDateTo(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            />
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              data-testid="ask-ai-use-all-transactions"
              checked={useAllTransactions}
              onChange={(e) => setUseAllTransactions(e.target.checked)}
            />
            Use all transactions
          </label>
        </div>

        <button
          type="submit"
          data-testid="ask-ai-submit"
          disabled={!question.trim() || mutation.isPending}
          className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
        >
          {mutation.isPending ? "Thinking..." : "Ask"}
        </button>
      </form>

      {mutation.isError && (
        <p
          data-testid="ask-ai-error"
          className="mt-4 rounded bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300"
        >
          {errorMessage(mutation.error)}
        </p>
      )}

      {mutation.isSuccess && (
        <div
          data-testid="ask-ai-answer"
          className="mt-4 rounded border border-slate-200 p-4 text-sm dark:border-slate-700"
        >
          <p className="whitespace-pre-wrap">{mutation.data.answer}</p>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            Based on {mutation.data.transactionsConsidered} transaction
            {mutation.data.transactionsConsidered === 1 ? "" : "s"}
            {mutation.data.truncated ? " (some older matches were left out to keep the request a reasonable size)" : ""}.
          </p>
        </div>
      )}
    </div>
  );
}
