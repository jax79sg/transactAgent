// Epic 13 (PBT-07): reusable, domain-shaped fast-check generators for the balance helpers, not raw primitives.
// Amounts are exact two-place strings the way the API sends them (negative, zero and very large included, with the
// edges where grouping and signs go wrong over-represented); "typed" amounts are the many ways a person spells one.

import fc from "fast-check";

import type { SeriesResponse } from "../src/api/types";
import { addDays } from "../src/lib/balances";
import { fromCents } from "../src/lib/money";

const LIMIT = 10n ** 18n;

/** Whole cents, biased toward the boundaries of thousands grouping and of zero. */
export const centsArb: fc.Arbitrary<bigint> = fc.oneof(
  { weight: 3, arbitrary: fc.bigInt({ min: -100_000n, max: 100_000n }) },
  { weight: 2, arbitrary: fc.bigInt({ min: -LIMIT, max: LIMIT }) },
  {
    weight: 1,
    arbitrary: fc.constantFrom(0n, 1n, -1n, 99n, 100n, 101n, 99_999n, 100_000n, 100_001n, 99_999_999n, 100_000_000n),
  },
);

/** An amount exactly as the API writes it: "1030.00", "-5.50", "0.00". Never "-0.00". */
export const amountArb: fc.Arbitrary<string> = centsArb.map(fromCents);

// Independent of the module under test, so a bug there cannot hide a bug here.
function groupWithCommas(digits: string): string {
  const groups: string[] = [];
  for (let end = digits.length; end > 0; end -= 3) groups.unshift(digits.slice(Math.max(0, end - 3), end));
  return groups.join(",");
}

/** An amount and one way a person might type it: grouped or not, shorter when exact, padded with spaces. */
export const typedAmountArb: fc.Arbitrary<{ amount: string; typed: string }> = fc
  .record({
    cents: centsArb,
    grouped: fc.boolean(),
    fractionChoice: fc.nat(3),
    before: fc.nat(3),
    after: fc.nat(3),
  })
  .map(({ cents, grouped, fractionChoice, before, after }) => {
    const amount = fromCents(cents);
    const negative = amount.startsWith("-");
    const [whole, fraction] = (negative ? amount.slice(1) : amount).split(".");
    const variants =
      fraction === "00" ? [".00", ".0", "", "."] : fraction.endsWith("0") ? [`.${fraction}`, `.${fraction[0]}`] : [`.${fraction}`];
    const typedWhole = grouped ? groupWithCommas(whole) : whole;
    const typed = `${" ".repeat(before)}${negative ? "-" : ""}${typedWhole}${variants[fractionChoice % variants.length]}${" ".repeat(after)}`;
    return { amount, typed };
  });

// Repeated names (and one differing only in case) so that ties are common and the tie-break is really exercised.
const ACCOUNT_NAMES = ["Alpha", "alpha", "Beta", "Savings", "Trust", "DBS", "OCBC"];

/**
 * A balance series as the API returns it: up to 15 accounts and up to 8 consecutive days, each account-day an exact
 * amount or a gap (about one in five), combined totals independent of the account cells (the chart helpers must not
 * assume they agree), and accounts that may never have a value at all.
 */
export const seriesArb: fc.Arbitrary<SeriesResponse> = fc
  .record({ accountCount: fc.integer({ min: 0, max: 15 }), pointCount: fc.integer({ min: 1, max: 8 }) })
  .chain(({ accountCount, pointCount }) => {
    const ids = Array.from({ length: accountCount }, (_, i) => `acct-${String(i).padStart(2, "0")}`);
    const cell = fc.option(amountArb, { nil: null, freq: 5 });
    return fc
      .record({
        names: fc.array(fc.constantFrom(...ACCOUNT_NAMES), { minLength: accountCount, maxLength: accountCount }),
        cells: fc.array(fc.array(cell, { minLength: accountCount, maxLength: accountCount }), {
          minLength: pointCount,
          maxLength: pointCount,
        }),
        combined: fc.array(cell, { minLength: pointCount, maxLength: pointCount }),
        granularity: fc.constantFrom<"day" | "month">("day", "month"),
      })
      .map(({ names, cells, combined, granularity }) => {
        const dates = Array.from({ length: pointCount }, (_, p) => addDays("2026-01-01", p));
        return {
          start: dates[0],
          end: dates[dates.length - 1],
          granularity,
          accounts: ids.map((id, i) => ({ accountId: id, name: names[i], currency: "SGD" })),
          missingAccounts: [],
          points: dates.map((date, p) => ({
            date,
            combinedSgd: combined[p],
            perAccount: Object.fromEntries(ids.map((id, i) => [id, cells[p][i]])),
            approximateAccountIds: [],
          })),
        };
      });
  });
