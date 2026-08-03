import { describe, expect, it } from "vitest";

import { askAiLinkFor } from "../src/pages/TransactionsPage";
import type { TransactionDTO } from "../src/api/types";

function makeTxn(overrides: Partial<TransactionDTO> = {}): TransactionDTO {
  return {
    id: "t1",
    transactionDate: "2026-01-15",
    description: "Mystery Wire Transfer",
    outFlow: "33000.00",
    inFlow: null,
    currency: "SGD",
    bankName: "DBS",
    category: { id: "c1", name: "UNSURE" },
    categorySource: "unsure",
    convertedAmountSgd: "33000.00",
    conversionIsApproximate: false,
    conversionUnavailable: false,
    bankStatementId: "bs1",
    ...overrides,
  };
}

describe("askAiLinkFor", () => {
  it("builds a link to the Ask AI page with a pre-filled question", () => {
    const link = askAiLinkFor(makeTxn());
    const url = new URL(link, "http://localhost");

    expect(url.pathname).toBe("/ask-ai");
    expect(url.searchParams.get("question")).toContain("Mystery Wire Transfer");
    expect(url.searchParams.get("question")).toContain("33000.00");
    expect(url.searchParams.get("question")).toContain("2026-01-15");
  });

  it("windows the date range to 30 days on either side of the transaction date", () => {
    const link = askAiLinkFor(makeTxn({ transactionDate: "2026-06-15" }));
    const url = new URL(link, "http://localhost");

    expect(url.searchParams.get("dateFrom")).toBe("2026-05-16");
    expect(url.searchParams.get("dateTo")).toBe("2026-07-15");
  });

  it("uses inFlow when the transaction has no outFlow", () => {
    const link = askAiLinkFor(makeTxn({ outFlow: null, inFlow: "500.00" }));
    const url = new URL(link, "http://localhost");

    expect(url.searchParams.get("question")).toContain("500.00");
  });
});
