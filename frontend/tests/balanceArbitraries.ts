// Epic 13 (PBT-07): reusable, domain-shaped fast-check generators for the balance helpers, not raw primitives.
// Amounts are exact two-place strings the way the API sends them (negative, zero and very large included, with the
// edges where grouping and signs go wrong over-represented); "typed" amounts are the many ways a person spells one.

import fc from "fast-check";

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
