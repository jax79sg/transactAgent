import { describe, expect, it } from "vitest";

import { UNKNOWN_VERSION, isReleaseNumber, parseVersion } from "../src/lib/parseVersion";

describe("parseVersion", () => {
  it.each([
    ["1.0.0", "1.0.0"],
    ["1.0.0\n", "1.0.0"],
    ["  12.34.56  \r\n", "12.34.56"],
    ["0.0.0", "0.0.0"],
  ])("reads %j as %s", (text, version) => {
    expect(parseVersion(text)).toBe(version);
  });

  it.each(["", "\n", "1.0", "1", "v1.0.0", "1.0.0-beta", "1.0.0.0", "one.two.three", "1.0.0 and more", "1.0.0\n2.0.0"])(
    "reads %j, which is not MAJOR.MINOR.PATCH, as unknown",
    (text) => {
      expect(parseVersion(text)).toBe(UNKNOWN_VERSION);
    },
  );

  it("reads a missing file as unknown", () => {
    expect(parseVersion(null)).toBe(UNKNOWN_VERSION);
    expect(parseVersion(undefined)).toBe(UNKNOWN_VERSION);
  });
});

describe("isReleaseNumber", () => {
  it("accepts exactly MAJOR.MINOR.PATCH", () => {
    expect(isReleaseNumber("1.2.3")).toBe(true);
    expect(isReleaseNumber("10.20.30")).toBe(true);
    expect(isReleaseNumber("1.2")).toBe(false);
    expect(isReleaseNumber("a1.2.3")).toBe(false);
    expect(isReleaseNumber("1.2.3a")).toBe(false);
    expect(isReleaseNumber("unknown")).toBe(false);
  });
});
