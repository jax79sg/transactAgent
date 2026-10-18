// Epic 13: exact money on the API's decimal strings. An amount arrives as a two-place string ("1030.00", "-5.50") and
// stays a string until it is shown. Nothing here uses Number or floating point: sums and differences are done on
// whole cents held as BigInt, so a figure the screen shows is exactly the figure the API computed (NFR-AB-1).
// Pure (no browser API, no locale): the same text on every machine and in tests.

const CANONICAL = /^(-?)(\d+)(?:\.(\d{1,2}))?$/;
const NOT_AVAILABLE = "—";

/** Whole cents of an amount string ("12.5" and "12" are accepted; more than two decimals are not). */
export function toCents(text: string): bigint {
  const match = CANONICAL.exec(text);
  if (!match) throw new Error(`not an amount with at most two decimal places: ${JSON.stringify(text)}`);
  const [, sign, whole, fraction = ""] = match;
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  return sign === "-" ? -cents : cents;
}

/** The canonical two-place string of whole cents. Zero is "0.00", never "-0.00". */
export function fromCents(cents: bigint): string {
  const negative = cents < 0n;
  const absolute = negative ? -cents : cents;
  const text = `${absolute / 100n}.${(absolute % 100n).toString().padStart(2, "0")}`;
  return negative ? `-${text}` : text;
}

export function addAmounts(a: string, b: string): string {
  return fromCents(toCents(a) + toCents(b));
}

export function subtractAmounts(a: string, b: string): string {
  return fromCents(toCents(a) - toCents(b));
}

/** The exact sum of any number of amounts ("0.00" for none). */
export function sumAmounts(values: readonly string[]): string {
  return fromCents(values.reduce((total, value) => total + toCents(value), 0n));
}

export function isNegativeAmount(text: string): boolean {
  return toCents(text) < 0n;
}

/** "1234567" -> "1,234,567". Digits only; the order of the digits never changes. */
function groupThousands(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/**
 * An amount for display: thousands grouped, always two decimals ("12,345.67", "-1,234.50"), and "0.00" for a
 * negative zero (the API prints a tiny negative converted amount as "-0.00"). A missing amount is "—", never "0.00".
 * Text that is not an amount is returned unchanged rather than hidden.
 */
export function formatAmount(text: string | null | undefined): string {
  if (text === null || text === undefined) return NOT_AVAILABLE;
  let cents: bigint;
  try {
    cents = toCents(text);
  } catch {
    return text;
  }
  const canonical = fromCents(cents);
  const negative = canonical.startsWith("-");
  const [whole, fraction] = (negative ? canonical.slice(1) : canonical).split(".");
  return `${negative ? "-" : ""}${groupThousands(whole)}.${fraction}`;
}

/** "SGD 12,345.67": the currency code first, as prose and tooltips write it. */
export function formatMoney(text: string | null | undefined, currency: string): string {
  if (text === null || text === undefined) return NOT_AVAILABLE;
  return `${currency} ${formatAmount(text)}`;
}

export type ParsedAmount =
  | { ok: true; value: string }
  | { ok: false; reason: "empty" | "not_a_number" | "too_many_decimals" };

// What a person types: optional "-", digits (optionally grouped by commas in threes), optional ".", optional decimals.
// No currency symbol, no exponent, no "+": a refused spelling is better than a guessed meaning.
const TYPED = /^(-?)(\d{1,3}(?:,\d{3})+|\d+)?(?:\.(\d*))?$/;

/**
 * An amount typed into a form -> the canonical two-place string to send ("1,234.5" -> "1234.50"), or why not. A third
 * decimal is refused, never rounded away ("never rounded for you", AR-53). The API remains the authority on range.
 */
export function parseAmountInput(text: string): ParsedAmount {
  const trimmed = text.trim();
  if (trimmed === "") return { ok: false, reason: "empty" };
  const match = TYPED.exec(trimmed);
  if (!match) return { ok: false, reason: "not_a_number" };
  const [, sign, whole = "", fraction = ""] = match;
  if (whole === "" && fraction === "") return { ok: false, reason: "not_a_number" }; // "-", ".", "-."
  if (fraction.length > 2) return { ok: false, reason: "too_many_decimals" };
  const digits = whole.replace(/,/g, "") || "0";
  return { ok: true, value: fromCents(toCents(`${sign}${digits}.${fraction.padEnd(2, "0")}`)) };
}
