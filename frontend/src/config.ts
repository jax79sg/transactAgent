/**
 * Runtime config (NFR Design pattern): reads window.__APP_CONFIG__, populated by
 * docker-entrypoint.sh at container startup from the API_BASE_URL env var -- not a
 * Vite build-time env var, so the same built image works regardless of deployment
 * address (see aidlc-docs/construction/frontend/nfr-design/nfr-design-patterns.md).
 *
 * Addendum (2026-08-02): API_BASE_URL is now an OPTIONAL override, not a required
 * fixed value. A real user hit this: accessing the app from a phone via the host
 * machine's LAN IP (http://192.168.x.x:8787) got a config.js hardcoded to
 * "http://localhost:7878" -- "localhost" on the phone means the phone itself, so
 * every API call (including login) silently failed to connect, with no server-side
 * trace at all since the request never left the phone. Default behavior is now to
 * derive the API's address from whatever host the page was actually loaded from
 * (same hostname, API's port), which works correctly for localhost, a LAN IP, or any
 * other hostname without needing reconfiguration. Set API_BASE_URL explicitly only
 * for setups where the API genuinely lives at a different host than the frontend.
 */

declare global {
  interface Window {
    __APP_CONFIG__?: {
      apiBaseUrl?: string;
    };
  }
}

const API_PORT = "7878";

function sameHostApiBaseUrl(): string {
  return `${window.location.protocol}//${window.location.hostname}:${API_PORT}`;
}

export const apiBaseUrl: string = window.__APP_CONFIG__?.apiBaseUrl || sameHostApiBaseUrl();
