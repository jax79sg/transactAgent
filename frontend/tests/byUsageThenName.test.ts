import { describe, expect, it } from "vitest";

import { byUsageThenName } from "../src/pages/TransactionsPage";
import type { CategoryDTO } from "../src/api/types";

function category(name: string, transactionCount: number): CategoryDTO {
  return { id: name, name, active: true, isReserved: false, transactionCount };
}

describe("byUsageThenName", () => {
  it("orders the top 10 most-used categories first, by usage descending", () => {
    // 12 categories -- more than the top-10 cutoff -- with usage strictly decreasing
    // so the expected top-10-by-usage order is unambiguous.
    const categories = Array.from({ length: 12 }, (_, i) => category(`Cat${12 - i}`, 12 - i));
    const sorted = byUsageThenName(categories);
    expect(sorted.slice(0, 10).map((c) => c.name)).toEqual([
      "Cat12", "Cat11", "Cat10", "Cat9", "Cat8", "Cat7", "Cat6", "Cat5", "Cat4", "Cat3",
    ]);
  });

  it("sorts everything past the top 10 alphabetically, not by usage", () => {
    // The 11th and 12th most-used ("Cat2" usage=2, "Cat1" usage=1) would stay in that
    // usage order under a pure usage sort -- alphabetically they must flip.
    const categories = Array.from({ length: 12 }, (_, i) => category(`Cat${12 - i}`, 12 - i));
    const sorted = byUsageThenName(categories);
    expect(sorted.slice(10).map((c) => c.name)).toEqual(["Cat1", "Cat2"]);
  });

  it("breaks top-10 ties alphabetically", () => {
    const sorted = byUsageThenName([category("Zoo", 5), category("Apple", 5), category("Mango", 5)]);
    expect(sorted.map((c) => c.name)).toEqual(["Apple", "Mango", "Zoo"]);
  });

  it("with 10 or fewer categories, behaves as a plain usage sort (no alphabetical-only tail)", () => {
    const sorted = byUsageThenName([category("Rare", 1), category("Common", 50), category("Medium", 10)]);
    expect(sorted.map((c) => c.name)).toEqual(["Common", "Medium", "Rare"]);
  });

  it("a newly-added zero-usage category sorts alphabetically among the other unused ones, not at the very end by insertion order", () => {
    const categories = [
      ...Array.from({ length: 10 }, (_, i) => category(`Used${10 - i}`, 10 - i)), // top 10, usage 10..1
      category("Zebra", 0),
      category("Transfer", 0),
      category("Apple", 0),
    ];
    const sorted = byUsageThenName(categories);
    expect(sorted.slice(10).map((c) => c.name)).toEqual(["Apple", "Transfer", "Zebra"]);
  });

  it("does not mutate the input array", () => {
    const input = [category("B", 1), category("A", 2)];
    const original = [...input];
    byUsageThenName(input);
    expect(input).toEqual(original);
  });
});
