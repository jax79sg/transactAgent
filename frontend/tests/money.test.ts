import fc from "fast-check";
import { describe, expect, it } from "vitest";

import {
  addAmounts,
  formatAmount,
  formatMoney,
  fromCents,
  isNegativeAmount,
  parseAmountInput,
  subtractAmounts,
  sumAmounts,
  toCents,
} from "../src/lib/money";
import { amountArb, centsArb, typedAmountArb } from "./balanceArbitraries";

// Epic 13: exact money on strings. Examples pin the cases a person would check by eye; properties (PBT-02, PBT-03)
// pin the algebra over thousands of generated amounts. fast-check prints the failing seed and path; replay with
// fc.assert(property, { seed, path }) (see aidlc-docs/construction/frontend/code/account-balance-summary.md).

describe("toCents and fromCents", () => {
  it("reads whole cents from the API's strings", () => {
    expect(toCents("0.00")).toBe(0n);
    expect(toCents("1030.00")).toBe(103000n);
    expect(toCents("-5.50")).toBe(-550n);
    expect(toCents("12.5")).toBe(1250n);
    expect(toCents("12")).toBe(1200n);
    expect(toCents("-0.00")).toBe(0n);
  });

  it("refuses what is not an amount with at most two decimals, rather than rounding it", () => {
    for (const bad of ["1.234", "1.230", "", "abc", "1,000.00", "1e5", " 1.00", "1.", ".5", "--1", "+1.00"]) {
      expect(() => toCents(bad), bad).toThrow();
    }
  });

  it("writes cents back as the canonical two-place string, never a negative zero", () => {
    expect(fromCents(0n)).toBe("0.00");
    expect(fromCents(5n)).toBe("0.05");
    expect(fromCents(-5n)).toBe("-0.05");
    expect(fromCents(103000n)).toBe("1030.00");
    expect(fromCents(123456789n)).toBe("1234567.89");
    expect(fromCents(10n ** 18n)).toBe("10000000000000000.00");
  });

  it("round-trips any number of cents", () => {
    fc.assert(fc.property(centsArb, (cents) => toCents(fromCents(cents)) === cents));
  });

  it("round-trips any canonical amount string", () => {
    fc.assert(fc.property(amountArb, (amount) => fromCents(toCents(amount)) === amount));
  });
});

describe("exact arithmetic", () => {
  it("adds and subtracts without the rounding floating point would add", () => {
    expect(addAmounts("0.10", "0.20")).toBe("0.30"); // 0.1 + 0.2 is 0.30000000000000004 as floats
    expect(subtractAmounts("1100.00", "1030.00")).toBe("70.00");
    expect(subtractAmounts("5.00", "7.50")).toBe("-2.50");
    expect(addAmounts("-5.50", "5.50")).toBe("0.00");
    expect(sumAmounts([])).toBe("0.00");
    expect(sumAmounts(["100.00", "-5.50", "0.05"])).toBe("94.55");
    expect(sumAmounts(["9999999999999999.99", "0.01"])).toBe("10000000000000000.00");
  });

  it("knows a negative amount", () => {
    expect(isNegativeAmount("-0.01")).toBe(true);
    expect(isNegativeAmount("0.00")).toBe(false);
    expect(isNegativeAmount("-0.00")).toBe(false);
    expect(isNegativeAmount("12.00")).toBe(false);
  });

  it("addition is commutative and associative", () => {
    fc.assert(fc.property(amountArb, amountArb, (a, b) => addAmounts(a, b) === addAmounts(b, a)));
    fc.assert(
      fc.property(amountArb, amountArb, amountArb, (a, b, c) => addAmounts(addAmounts(a, b), c) === addAmounts(a, addAmounts(b, c))),
    );
  });

  it("subtraction undoes addition, and an amount minus itself is zero", () => {
    fc.assert(fc.property(amountArb, amountArb, (a, b) => subtractAmounts(addAmounts(a, b), b) === a));
    fc.assert(fc.property(amountArb, (a) => subtractAmounts(a, a) === "0.00"));
  });

  it("a sum is the same in any order and equals folding addition", () => {
    fc.assert(
      fc.property(fc.array(amountArb, { maxLength: 12 }), (values) => {
        const folded = values.reduce((total, value) => addAmounts(total, value), "0.00");
        return sumAmounts(values) === folded && sumAmounts([...values].reverse()) === folded;
      }),
    );
  });
});

describe("formatAmount and formatMoney", () => {
  it.each([
    ["0.00", "0.00"],
    ["0.05", "0.05"],
    ["999.99", "999.99"],
    ["1000.00", "1,000.00"],
    ["12345.67", "12,345.67"],
    ["1234567.89", "1,234,567.89"],
    ["-1234.50", "-1,234.50"],
    ["-0.01", "-0.01"],
    ["100.00", "100.00"],
    ["10000000000000000.00", "10,000,000,000,000,000.00"],
  ])("groups %s as %s", (input, expected) => {
    expect(formatAmount(input)).toBe(expected);
  });

  it("never shows a negative zero", () => {
    expect(formatAmount("-0.00")).toBe("0.00");
  });

  it("shows an amount that is not there as a dash, never as 0.00", () => {
    expect(formatAmount(null)).toBe("—");
    expect(formatAmount(undefined)).toBe("—");
    expect(formatMoney(null, "SGD")).toBe("—");
  });

  it("returns text that is not an amount unchanged rather than hiding it", () => {
    expect(formatAmount("abc")).toBe("abc");
  });

  it("puts the currency code first", () => {
    expect(formatMoney("1030.00", "SGD")).toBe("SGD 1,030.00");
    expect(formatMoney("-5.50", "USD")).toBe("USD -5.50");
  });

  it("is the same digits, in the same order, with only commas added", () => {
    fc.assert(
      fc.property(amountArb, (amount) => {
        const shown = formatAmount(amount);
        expect(shown.replace(/,/g, "")).toBe(amount);
        expect(shown).toMatch(/^-?\d{1,3}(,\d{3})*\.\d{2}$/);
      }),
    );
  });
});

describe("parseAmountInput", () => {
  it.each([
    ["1234.5", "1234.50"],
    ["1,234.50", "1234.50"],
    ["-12.3", "-12.30"],
    ["  7  ", "7.00"],
    [".5", "0.50"],
    ["5.", "5.00"],
    ["0", "0.00"],
    ["-0", "0.00"],
    ["007.5", "7.50"],
    ["1,234,567", "1234567.00"],
    ["12.00", "12.00"],
    ["9999999999999999.99", "9999999999999999.99"],
  ])("reads %s as %s", (typed, canonical) => {
    expect(parseAmountInput(typed)).toEqual({ ok: true, value: canonical });
  });

  it.each([
    ["", "empty"],
    ["   ", "empty"],
    ["abc", "not_a_number"],
    ["1e5", "not_a_number"],
    ["NaN", "not_a_number"],
    ["Infinity", "not_a_number"],
    ["--1", "not_a_number"],
    ["+5", "not_a_number"],
    ["-", "not_a_number"],
    [".", "not_a_number"],
    ["1,2,3", "not_a_number"],
    ["1234,567", "not_a_number"],
    ["S$100", "not_a_number"],
    ["1 000", "not_a_number"],
    ["12.345", "too_many_decimals"],
    ["12.340", "too_many_decimals"],
    ["0.001", "too_many_decimals"],
  ])("refuses %s (%s)", (typed, reason) => {
    expect(parseAmountInput(typed)).toEqual({ ok: false, reason });
  });

  it("reads every spelling of an amount as that amount (PBT round trip)", () => {
    fc.assert(
      fc.property(typedAmountArb, ({ amount, typed }) => {
        expect(parseAmountInput(typed)).toEqual({ ok: true, value: amount });
      }),
    );
  });

  it("reads back what formatAmount shows (PBT round trip)", () => {
    fc.assert(
      fc.property(amountArb, (amount) => {
        expect(parseAmountInput(formatAmount(amount))).toEqual({ ok: true, value: amount });
      }),
    );
  });

  it("never produces more than two decimals or a negative zero (PBT)", () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 20 }), (text) => {
        const result = parseAmountInput(text);
        if (result.ok) {
          expect(result.value).toMatch(/^-?\d+\.\d{2}$/);
          expect(result.value).not.toBe("-0.00");
        }
      }),
    );
  });
});
