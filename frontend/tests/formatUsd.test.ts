import { describe, expect, it } from "vitest";

import { formatCount, formatUsd } from "../src/lib/formatUsd";

describe("formatUsd", () => {
  it.each([
    [0, "$0.00"],
    ["0", "$0.00"],
    ["0.00000000", "$0.00"],
    [1, "$1.00"],
    [2.5, "$2.50"],
    ["1234.5", "$1,234.50"],
    [0.0123, "$0.0123"],
    ["0.00046000", "$0.0005"],
    [0.0001, "$0.0001"],
    [0.99996, "$1.0000"],
  ])("shows %s as %s", (value, text) => {
    expect(formatUsd(value)).toBe(text);
  });

  it("shows an amount below a hundredth of a cent as less than that, never as zero", () => {
    expect(formatUsd(0.000004)).toBe("<$0.0001");
  });

  it("keeps four decimals under a dollar so a cheap day is not shown as free", () => {
    expect(formatUsd(0.0034)).toBe("$0.0034");
  });

  it("treats junk as zero rather than printing NaN", () => {
    expect(formatUsd("soon")).toBe("$0.00");
    expect(formatUsd(Number.NaN)).toBe("$0.00");
  });

  it("marks a negative amount", () => {
    expect(formatUsd(-1.5)).toBe("-$1.50");
  });
});

describe("formatCount", () => {
  it("adds thousands separators", () => {
    expect(formatCount(0)).toBe("0");
    expect(formatCount(1234567)).toBe("1,234,567");
  });
});
