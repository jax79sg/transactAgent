import { isReleaseNumber } from "./parseVersion";

/** Where the published user guide lives (GitHub Pages, from the repository's docs/ folder): the latest guide at the
 * root, every release's own copy under /v<version>/, and an index of all of them. */
export const GUIDE_BASE_URL = "https://jax79sg.github.io/transactAgent/";
export const RELEASES_URL = `${GUIDE_BASE_URL}releases.html`;

/** The guide for one release; an "unknown" or malformed version has no archive, so it gets the latest guide. */
export function guideUrlFor(version: string): string {
  return isReleaseNumber(version) ? `${GUIDE_BASE_URL}v${version}/` : GUIDE_BASE_URL;
}
