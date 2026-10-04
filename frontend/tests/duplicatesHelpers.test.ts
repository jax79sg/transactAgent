import { describe, expect, it } from "vitest";

import { ApiError } from "../src/api/client";
import {
  duplicateErrorMessage,
  errorCode,
  formatPeriod,
  formatStatementLabel,
  STALE_ACTION_ERRORS,
} from "../src/lib/duplicates";

const err = (error: string, message = "server says no") => new ApiError(409, { error, message });

describe("formatPeriod", () => {
  it("writes a period within one year with the year once", () => {
    expect(formatPeriod("2026-06-02", "2026-06-30")).toBe("2 Jun to 30 Jun 2026");
  });

  it("writes both years when the period crosses a year end", () => {
    expect(formatPeriod("2025-12-28", "2026-01-03")).toBe("28 Dec 2025 to 3 Jan 2026");
  });

  it("handles a one-day period and the first and last days of the year", () => {
    expect(formatPeriod("2026-02-28", "2026-02-28")).toBe("28 Feb to 28 Feb 2026");
    expect(formatPeriod("2026-01-01", "2026-12-31")).toBe("1 Jan to 31 Dec 2026");
  });

  it("does not depend on the time zone (dates are read from the text, never through Date)", () => {
    // A statement dated the 1st must never be shown as the 31st of the previous month.
    expect(formatPeriod("2026-03-01", "2026-03-01")).toBe("1 Mar to 1 Mar 2026");
  });

  it("accepts a full timestamp by using only its date part", () => {
    expect(formatPeriod("2026-06-02T00:00:00Z", "2026-06-30T23:59:59Z")).toBe("2 Jun to 30 Jun 2026");
  });
});

describe("formatStatementLabel", () => {
  const base = { periodStart: "2026-06-02", periodEnd: "2026-06-30" };

  it("is '<file name> (<bank>, <period>)'", () => {
    expect(formatStatementLabel({ ...base, fileName: "JUN 2026_0728.pdf", bankName: "UOB" })).toBe(
      "JUN 2026_0728.pdf (UOB, 2 Jun to 30 Jun 2026)",
    );
  });

  it("falls back to the bank and the period when the file name could not be resolved", () => {
    expect(formatStatementLabel({ ...base, fileName: null, bankName: "UOB" })).toBe("UOB (2 Jun to 30 Jun 2026)");
  });

  it("falls back to 'a statement' when there is neither", () => {
    expect(formatStatementLabel({ ...base, fileName: null, bankName: null })).toBe("a statement (2 Jun to 30 Jun 2026)");
  });

  it("omits a missing bank rather than printing 'null'", () => {
    expect(formatStatementLabel({ ...base, fileName: "a.pdf", bankName: null })).toBe("a.pdf (2 Jun to 30 Jun 2026)");
  });
});

describe("duplicateErrorMessage", () => {
  it.each([
    ["pair_not_pending", "already been decided"],
    ["removal_not_offered", "differ in size"],
    ["removal_already_requested", "already in progress"],
    ["statement_missing", "no longer exists"],
    ["not_a_skipped_file", "no skipped file"],
  ])("explains %s in plain words", (code, fragment) => {
    expect(duplicateErrorMessage(err(code))).toContain(fragment);
  });

  it("passes the server's own sentence through for an out-of-date confirmation, which names what changed", () => {
    expect(duplicateErrorMessage(err("confirmation_out_of_date", "The manual corrections changed from 0 to 1. Please review again."))).toBe(
      "The manual corrections changed from 0 to 1. Please review again.",
    );
  });

  it("uses the server message for an unknown code and a generic one for a non-API error", () => {
    expect(duplicateErrorMessage(err("something_new", "Try later"))).toBe("Try later");
    expect(duplicateErrorMessage(new Error("network"))).toBe("Something went wrong. Please try again.");
  });
});

describe("errorCode and STALE_ACTION_ERRORS", () => {
  it("reads the code from an API error and nothing from anything else", () => {
    expect(errorCode(err("pair_not_pending"))).toBe("pair_not_pending");
    expect(errorCode(new Error("x"))).toBeNull();
  });

  it("treats exactly the 'what you were looking at changed' codes as stale", () => {
    expect([...STALE_ACTION_ERRORS].sort()).toEqual(
      ["confirmation_out_of_date", "pair_not_pending", "removal_already_requested", "removal_not_offered", "statement_missing"].sort(),
    );
    expect(STALE_ACTION_ERRORS.has("not_a_skipped_file")).toBe(false);
  });
});
