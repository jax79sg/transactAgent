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

// Every sort column the type allows. A Record, so a value added to SortByOption fails to compile here until it is
// listed -- and so is tested below -- rather than being silently left out (issue #23).
const SORT_COLUMNS: Record<SortByOption, true> = {
  date: true, amount: true, category: true, bank: true, description: true, converted: true,
};

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
    sortBy: fc.constantFrom<SortByOption>(...(Object.keys(SORT_COLUMNS) as SortByOption[])),
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


describe("sort column in the URL (issue #23)", () => {
  it.each(Object.keys(SORT_COLUMNS) as SortByOption[])("keeps a sort by %s through the URL, both directions", (sortBy) => {
    for (const sortDir of ["asc", "desc"] as SortDir[]) {
      const params = filterStateToSearchParams({ sortBy, sortDir });

      expect(params.get("sortBy")).toBe(sortBy);
      expect(searchParamsToFilterState(params)).toEqual({ sortBy, sortDir });
    }
  });

  it("reads a sort by description from a link, as the page does when it is opened", () => {
    expect(searchParamsToFilterState(new URLSearchParams("sortBy=description&sortDir=asc"))).toEqual({
      sortBy: "description",
      sortDir: "asc",
    });
  });

  it("still drops a column it does not know", () => {
    expect(searchParamsToFilterState(new URLSearchParams("sortBy=colour&sortDir=asc"))).toEqual({ sortDir: "asc" });
  });
});
