import { describe, expect, it } from "vitest";

import { byUsageThenName } from "../src/pages/TransactionsPage";
import type { CategoryDTO } from "../src/api/types";

function category(name: string, transactionCount: number): CategoryDTO {
  return { id: name, name, active: true, isReserved: false, transactionCount };
}

describe("byUsageThenName", () => {
  it("orders most-used categories first", () => {
    const sorted = byUsageThenName([category("Rare", 1), category("Common", 50), category("Medium", 10)]);
    expect(sorted.map((c) => c.name)).toEqual(["Common", "Medium", "Rare"]);
  });

  it("breaks ties alphabetically", () => {
    const sorted = byUsageThenName([category("Zoo", 5), category("Apple", 5), category("Mango", 5)]);
    expect(sorted.map((c) => c.name)).toEqual(["Apple", "Mango", "Zoo"]);
  });

  it("does not mutate the input array", () => {
    const input = [category("B", 1), category("A", 2)];
    const original = [...input];
    byUsageThenName(input);
    expect(input).toEqual(original);
  });
});
