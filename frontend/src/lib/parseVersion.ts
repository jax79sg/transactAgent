/** The release number as MAJOR.MINOR.PATCH (issue #27). Kept free of Node and browser APIs so the build
 * (vite.config.ts) and the tests can both use it. */
const RELEASE_NUMBER = /^\d+\.\d+\.\d+$/;

export const UNKNOWN_VERSION = "unknown";

export function isReleaseNumber(version: string): boolean {
  return RELEASE_NUMBER.test(version);
}

/** What the build makes of the VERSION file's text: the number if it is one, otherwise "unknown" (a missing or
 * malformed file must not stop the build). */
export function parseVersion(text: string | null | undefined): string {
  const trimmed = (text ?? "").trim();
  return isReleaseNumber(trimmed) ? trimmed : UNKNOWN_VERSION;
}
