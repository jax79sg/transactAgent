import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { ApiError } from "../src/api/client";
import type { AccountDTO, AccountType } from "../src/api/types";
import {
  addDays,
  BALANCE_ERROR_MESSAGES,
  type BalanceErrorCode,
  balanceErrorMessage,
  dayBefore,
  describeBasis,
  describeExclusions,
  describeUnlinked,
  describeLookup,
  isAccountGone,
  joinList,
  localToday,
  mergeTypeOutcome,
  monthOf,
  nextAccountNeedingBalance,
  pluralize,
  TYPE_NOUNS,
} from "../src/lib/balances";

function account(overrides: Partial<AccountDTO> = {}): AccountDTO {
  return {
    id: "a",
    name: "A",
    bankName: "DBS",
    accountIdentifier: "1",
    type: "deposit",
    typeSetByUser: false,
    currency: "SGD",
    anchor: null,
    canHaveAnchor: true,
    statementCount: 1,
    transactionCount: 0,
    closingBalanceCount: 0,
    latestTransactionDate: null,
    ...overrides,
  };
}

describe("describeBasis", () => {
  it("words an entered balance and a statement closing balance in the owner's terms", () => {
    expect(describeBasis({ source: "anchor", date: "2026-10-05" })).toBe("your entered balance of 5 Oct 2026");
    expect(describeBasis({ source: "statement_closing", date: "2026-08-31" })).toBe("the statement closing balance of 31 Aug 2026");
  });
});

describe("describeLookup", () => {
  const today = "2026-10-18";
  it("states a date lookup's day", () => {
    expect(describeLookup({ resolvedDate: "2026-07-31", today, requestedMonth: null })).toBe("Balances at the end of 31 Jul 2026");
  });
  it("states the day a past month resolved to", () => {
    expect(describeLookup({ resolvedDate: "2026-09-30", today, requestedMonth: "2026-09" })).toBe(
      "Balances at the end of September 2026 (30 Sep 2026)",
    );
  });
  it("says the current month is so far, and to which day", () => {
    expect(describeLookup({ resolvedDate: "2026-10-18", today, requestedMonth: "2026-10" })).toBe(
      "Balances for October 2026 so far (to 18 Oct 2026, today)",
    );
  });
  it("handles February in a leap year", () => {
    expect(describeLookup({ resolvedDate: "2028-02-29", today, requestedMonth: "2028-02" })).toBe(
      "Balances at the end of February 2028 (29 Feb 2028)",
    );
  });
});

describe("localToday", () => {
  it("uses the LOCAL calendar date, not the UTC one", () => {
    // 01:30 on 18 Oct in Singapore is still 17 Oct in UTC: the fake exposes only the local getters, so a version that
    // went through toISOString() could not even be written against this type.
    const singaporeEarlyMorning = { getFullYear: () => 2026, getMonth: () => 9, getDate: () => 18 };
    expect(localToday(singaporeEarlyMorning)).toBe("2026-10-18");
  });
  it("pads single-digit months and days", () => {
    expect(localToday({ getFullYear: () => 2026, getMonth: () => 0, getDate: () => 5 })).toBe("2026-01-05");
  });
  it("defaults to the real clock and gives a plausible date", () => {
    expect(localToday()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("addDays and dayBefore", () => {
  it.each([
    ["2026-10-18", "2026-10-17"],
    ["2026-10-01", "2026-09-30"],
    ["2026-01-01", "2025-12-31"],
    ["2024-03-01", "2024-02-29"], // leap year
    ["2025-03-01", "2025-02-28"],
    ["2000-01-01", "1999-12-31"],
  ])("the day before %s is %s", (day, before) => {
    expect(dayBefore(day)).toBe(before);
  });

  it("moves forward too", () => {
    expect(addDays("2026-02-28", 1)).toBe("2026-03-01");
    expect(addDays("2024-02-28", 2)).toBe("2024-03-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });

  it("monthOf keeps the year and month", () => {
    expect(monthOf("2026-10-18")).toBe("2026-10");
  });

  it("dayBefore undoes the next day, for any date (PBT)", () => {
    const dayArb = fc.date({ min: new Date(Date.UTC(2000, 0, 1)), max: new Date(Date.UTC(2100, 11, 31)), noInvalidDate: true }).map((d) =>
      d.toISOString().slice(0, 10),
    );
    fc.assert(
      fc.property(dayArb, fc.integer({ min: -4000, max: 4000 }), (day, n) => {
        expect(addDays(addDays(day, n), -n)).toBe(day);
        expect(dayBefore(addDays(day, 1))).toBe(day);
      }),
    );
  });
});

describe("mergeTypeOutcome: parity with the API's rule (AR-54)", () => {
  // The API: `if not survivor.type_user_set and absorbed.type_user_set: survivor takes the absorbed type, flag set`.
  // Its tests: test_the_survivor_keeps_its_type_unless_only_the_absorbed_ones_was_set_by_the_user and
  // test_a_type_the_survivors_user_chose_is_not_overwritten. The other two flag combinations are listed here too.
  const cases: { survivorSet: boolean; absorbedSet: boolean; takesAbsorbed: boolean }[] = [
    { survivorSet: false, absorbedSet: false, takesAbsorbed: false },
    { survivorSet: false, absorbedSet: true, takesAbsorbed: true },
    { survivorSet: true, absorbedSet: false, takesAbsorbed: false },
    { survivorSet: true, absorbedSet: true, takesAbsorbed: false },
  ];
  const types: AccountType[] = ["deposit", "credit_card", "unknown"];

  it.each(cases)("survivor set=$survivorSet, absorbed set=$absorbedSet", ({ survivorSet, absorbedSet, takesAbsorbed }) => {
    for (const survivorType of types) {
      for (const absorbedType of types) {
        const outcome = mergeTypeOutcome(
          { type: absorbedType, typeSetByUser: absorbedSet },
          { type: survivorType, typeSetByUser: survivorSet },
        );
        expect(outcome.type).toBe(takesAbsorbed ? absorbedType : survivorType);
        expect(outcome.typeSetByUser).toBe(takesAbsorbed ? true : survivorSet);
        expect(outcome.changed).toBe(takesAbsorbed && absorbedType !== survivorType);
      }
    }
  });
});

describe("nextAccountNeedingBalance", () => {
  const anchor = { balance: "1.00", asOfDate: "2026-01-01", updatedAt: "2026-01-01T00:00:00Z" };
  const list = [
    account({ id: "has", anchor }),
    account({ id: "card", type: "credit_card", canHaveAnchor: false }),
    account({ id: "first" }),
    account({ id: "second" }),
  ];

  it("is the first deposit account with no balance, in list order", () => {
    expect(nextAccountNeedingBalance(list, [])?.id).toBe("first");
  });
  it("skips the accounts already handled in this run", () => {
    expect(nextAccountNeedingBalance(list, ["first"])?.id).toBe("second");
  });
  it("is null when none is left", () => {
    expect(nextAccountNeedingBalance(list, ["first", "second"])).toBeNull();
    expect(nextAccountNeedingBalance([], [])).toBeNull();
  });
  it("never offers a credit card or an unknown-type account", () => {
    expect(nextAccountNeedingBalance([account({ id: "x", type: "unknown", canHaveAnchor: false })], [])).toBeNull();
  });
});

describe("balanceErrorMessage", () => {
  // A Record over every code: a code added to BalanceErrorCode without wording fails to compile (see balances.ts).
  const ALL_CODES: Record<BalanceErrorCode, true> = {
    account_not_found: true,
    invalid_anchor_value: true,
    anchor_date_in_future: true,
    anchor_date_out_of_range: true,
    not_a_deposit_account: true,
    nothing_to_change: true,
    invalid_account_name: true,
    invalid_account_type: true,
    merge_same_account: true,
    merge_currency_mismatch: true,
    merge_appear_together: true,
    merge_anchor_choice_required: true,
    merge_anchor_choice_invalid: true,
    date_or_month_required: true,
    date_in_future: true,
    month_in_future: true,
    invalid_date_range: true,
    range_too_large: true,
  };

  it("words every one of the API's 18 codes, each with a sentence of its own meaning", () => {
    expect(Object.keys(ALL_CODES)).toHaveLength(18);
    for (const code of Object.keys(ALL_CODES) as BalanceErrorCode[]) {
      // The status is not what picks the sentence (the code is); 400 stands in for all of them.
      const status = 400;
      const message = balanceErrorMessage(new ApiError(status, { error: code, message: "server text" }));
      expect(message, code).toBe(BALANCE_ERROR_MESSAGES[code]);
      expect(message, code).not.toBe("server text");
      expect(message.length, code).toBeGreaterThan(10);
    }
  });

  it("tells the two-accounts-on-one-statement refusal to rename, since that is the owner's real case", () => {
    const message = balanceErrorMessage(new ApiError(409, { error: "merge_appear_together", message: "x" }));
    expect(message).toMatch(/rename/i);
  });

  it("words a framework 422 (a malformed date) itself, since it has no message", () => {
    expect(balanceErrorMessage(new ApiError(422, { detail: [] } as unknown as { error: string; message: string }))).toBe("That isn't a valid date.");
  });

  it("shows the server's own message for a code it does not know", () => {
    expect(balanceErrorMessage(new ApiError(400, { error: "something_new", message: "A new thing went wrong." }))).toBe("A new thing went wrong.");
  });

  it("falls back to a generic sentence when there is no message either", () => {
    expect(balanceErrorMessage(new ApiError(400, { error: "something_new", message: "" }))).toBe("Something went wrong. Please try again.");
  });

  it("does not show a server fault's status text as if it were a reason", () => {
    expect(balanceErrorMessage(new ApiError(500, { error: "unknown", message: "Internal Server Error" }))).toBe(
      "The server had a problem. Please try again.",
    );
  });

  it("says so when the server could not be reached", () => {
    expect(balanceErrorMessage(new TypeError("Failed to fetch"))).toBe("Couldn't reach the server.");
  });

  it("an object property name is not mistaken for a code", () => {
    expect(balanceErrorMessage(new ApiError(400, { error: "toString", message: "own message" }))).toBe("own message");
    expect(balanceErrorMessage(new ApiError(400, { error: "__proto__", message: "own message" }))).toBe("own message");
  });
});

describe("isAccountGone", () => {
  it("is true only for account_not_found", () => {
    expect(isAccountGone(new ApiError(404, { error: "account_not_found", message: "" }))).toBe(true);
    expect(isAccountGone(new ApiError(409, { error: "merge_appear_together", message: "" }))).toBe(false);
    expect(isAccountGone(new Error("x"))).toBe(false);
  });
});

describe("pluralize and TYPE_NOUNS", () => {
  it("puts the count with the right form", () => {
    expect(pluralize(0, "statement", "statements")).toBe("0 statements");
    expect(pluralize(1, "statement", "statements")).toBe("1 statement");
    expect(pluralize(2, "statement", "statements")).toBe("2 statements");
  });
  it("has a noun phrase for every type", () => {
    expect(TYPE_NOUNS).toEqual({
      deposit: "a savings or current account",
      credit_card: "a credit card",
      unknown: "an account of unknown type",
    });
  });
});

describe("joinList", () => {
  it("joins in plain English", () => {
    expect(joinList([])).toBe("");
    expect(joinList(["a"])).toBe("a");
    expect(joinList(["a", "b"])).toBe("a and b");
    expect(joinList(["a", "b", "c"])).toBe("a, b and c");
  });
});

describe("describeUnlinked", () => {
  const base = { count: 99, bankNames: ["GXS Bank"], earliestDate: "2026-07-01", latestDate: "2026-07-31", netByCurrency: [{ currency: "SGD", net: "18.65" }] };

  it("states how many, from where, when, the net, and that they are left out", () => {
    expect(describeUnlinked(base)).toBe(
      "99 transactions from GXS Bank, dated 1 Jul to 31 Jul 2026 (net SGD 18.65), belong to no account, so they are left out of every balance.",
    );
  });
  it("uses the singular for one transaction, with a single date", () => {
    expect(describeUnlinked({ ...base, count: 1, earliestDate: "2026-07-31" })).toBe(
      "1 transaction from GXS Bank, dated 31 Jul 2026 (net SGD 18.65), belongs to no account, so it is left out of every balance.",
    );
  });
  it("lists several banks and keeps currencies apart rather than adding them", () => {
    const text = describeUnlinked({
      ...base,
      bankNames: ["DBS", "GXS Bank"],
      netByCurrency: [{ currency: "SGD", net: "100.00" }, { currency: "USD", net: "-5.50" }],
    });
    expect(text).toContain("from DBS and GXS Bank");
    expect(text).toContain("(net SGD 100.00 and USD -5.50)");
  });
  it("spans a year end", () => {
    expect(describeUnlinked({ ...base, earliestDate: "2025-12-30", latestDate: "2026-01-02" })).toContain("dated 30 Dec 2025 to 2 Jan 2026");
  });
});

describe("describeExclusions", () => {
  it("names every excluded account with its reason", () => {
    expect(
      describeExclusions([
        { accountId: "1", name: "Fresh", reason: "anchor_required" },
        { accountId: "2", name: "Offshore EUR", reason: "fx_unavailable" },
      ]),
    ).toBe("Not included: Fresh (anchor required), Offshore EUR (no exchange rate)");
  });
  it("is empty when nothing is excluded", () => {
    expect(describeExclusions([])).toBe("");
  });
});
