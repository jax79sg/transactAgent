import { describe, expect, it } from "vitest";

import { appVersion } from "../src/version";

describe("appVersion", () => {
  it("is the release number read from the repository's VERSION file at build time, not a fallback", () => {
    // "unknown" is what the build falls back to when it cannot find or understand the file
    expect(appVersion).toMatch(/^\d+\.\d+\.\d+$/);
  });
});
