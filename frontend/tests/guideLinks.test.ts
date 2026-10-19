import { describe, expect, it } from "vitest";

import { GUIDE_BASE_URL, RELEASES_URL, guideUrlFor } from "../src/lib/guideLinks";

describe("guideUrlFor", () => {
  it("points a release at its own copy of the guide", () => {
    expect(guideUrlFor("1.0.0")).toBe("https://jax79sg.github.io/transactAgent/v1.0.0/");
    expect(guideUrlFor("12.34.56")).toBe("https://jax79sg.github.io/transactAgent/v12.34.56/");
  });

  it.each(["unknown", "", "1.0", "v1.0.0", "1.0.0-beta", "../../etc", "1.0.0/../x"])(
    "sends %j, which has no archived guide, to the latest one",
    (version) => {
      expect(guideUrlFor(version)).toBe(GUIDE_BASE_URL);
    },
  );

  it("keeps the base address as a folder so the paths under it resolve", () => {
    expect(GUIDE_BASE_URL.endsWith("/")).toBe(true);
    expect(RELEASES_URL).toBe(`${GUIDE_BASE_URL}releases.html`);
  });
});
