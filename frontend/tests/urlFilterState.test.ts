import fc from "fast-check";
import { describe, expect, it } from "vitest";

import type {
  CategorySourceValue,
  FlowDirection,
  GroupByOption,
  SortByOption,
  SortDir,
  TransactionFilterState,
} from "../src/api/types";
import { filterStateToSearchParams, searchParamsToFilterState } from "../src/lib/urlFilterState";

const filterStateArbitrary: fc.Arbitrary<TransactionFilterState> = fc.record(
  {
    dateFrom: fc.date({ min: new Date(2000, 0, 1), max: new Date(2100, 0, 1) }).map((d) => d.toISOString().slice(0, 10)),
    dateTo: fc.date({ min: new Date(2000, 0, 1), max: new Date(2100, 0, 1) }).map((d) => d.toISOString().slice(0, 10)),
    bank: fc.string({ minLength: 1, maxLength: 20 }),
    category: fc.string({ minLength: 1, maxLength: 20 }),
    currency: fc.constantFrom("SGD", "USD", "EUR"),
    textSearch: fc.string({ minLength: 1, maxLength: 30 }),
    flowDirection: fc.constantFrom<FlowDirection>("in", "out"),
    categorySource: fc.constantFrom<CategorySourceValue>("similarity", "llm", "manual", "unsure"),
    groupBy: fc.constantFrom<GroupByOption>("category", "bank", "month", "categorySource"),
    sortBy: fc.constantFrom<SortByOption>("date", "amount", "category", "bank"),
    sortDir: fc.constantFrom<SortDir>("asc", "desc"),
    page: fc.integer({ min: 1, max: 1000 }),
    pageSize: fc.integer({ min: 1, max: 200 }),
  },
  { requiredKeys: [] },
);

describe("filter state <-> URL round-trip (PBT)", () => {
  it("is lossless for any generated filter state", () => {
    fc.assert(
      fc.property(filterStateArbitrary, (state) => {
        const params = filterStateToSearchParams(state);
        const roundTripped = searchParamsToFilterState(params);
        expect(roundTripped).toEqual(state);
      }),
    );
  });

  it("an empty filter state produces an empty query string", () => {
    const params = filterStateToSearchParams({});
    expect(params.toString()).toBe("");
  });

  it("round-tripping twice is idempotent", () => {
    fc.assert(
      fc.property(filterStateArbitrary, (state) => {
        const once = searchParamsToFilterState(filterStateToSearchParams(state));
        const twice = searchParamsToFilterState(filterStateToSearchParams(once));
        expect(twice).toEqual(once);
      }),
    );
  });

  it("unrecognized enum values in the URL are dropped, not silently accepted", () => {
    const params = new URLSearchParams("flowDirection=sideways&sortDir=upside-down");
    const state = searchParamsToFilterState(params);
    expect(state.flowDirection).toBeUndefined();
    expect(state.sortDir).toBeUndefined();
  });
});
