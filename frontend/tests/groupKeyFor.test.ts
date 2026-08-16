import { describe, expect, it } from "vitest";

import { groupKeyFor } from "../src/pages/TransactionsPage";
import type { TransactionDTO } from "../src/api/types";

// This must stay in lockstep with api_service/transactions/repository.py's
// _GROUP_KEY_EXPRESSIONS -- a client-side key that doesn't match the server's
// group_key string means every row silently falls out of every group header (the
// exact class of bug this whole feature needed fixing for in the first place).
function makeTxn(overrides: Partial<TransactionDTO> = {}): TransactionDTO {
  return {
    id: "t1",
    transactionDate: "2026-03-15",
    description: "Test",
    outFlow: "10.00",
    inFlow: null,
    currency: "SGD",
    bankName: "DBS",
    category: { id: "c1", name: "Groceries" },
    categorySource: "manual",
    convertedAmountSgd: "10.00",
    conversionIsApproximate: false,
    conversionUnavailable: false,
    bankStatementId: "bs1",
    embeddingStatus: "pending",
    ...overrides,
  };
}

describe("groupKeyFor", () => {
  it("category: matches Category.name", () => {
    expect(groupKeyFor(makeTxn({ category: { id: "c1", name: "Dining" } }), "category")).toBe("Dining");
  });

  it("bank: matches Transaction.bank_name", () => {
    expect(groupKeyFor(makeTxn({ bankName: "OCBC" }), "bank")).toBe("OCBC");
  });

  it("month: matches to_char(date, 'YYYY-MM') -- the date truncated to year-month", () => {
    expect(groupKeyFor(makeTxn({ transactionDate: "2026-03-15" }), "month")).toBe("2026-03");
  });

  it("categorySource: matches the plain enum value, not a Python repr", () => {
    expect(groupKeyFor(makeTxn({ categorySource: "manual" }), "categorySource")).toBe("manual");
  });
});
