/** US-dollar amounts for the Costs page. Model calls cost fractions of a cent each, so an amount under a dollar keeps
 * four decimals (two would show most days as "$0.00"); a dollar or more reads as ordinary money. */
export function formatUsd(value: number | string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount === 0) return "$0.00";
  const abs = Math.abs(amount);
  if (abs < 0.0001) return amount < 0 ? "-<$0.0001" : "<$0.0001";
  const digits = abs >= 1 ? 2 : 4;
  const text = abs.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${amount < 0 ? "-" : ""}$${text}`;
}

/** Whole numbers (calls, tokens) with thousands separators. */
export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}
