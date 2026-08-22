#!/bin/sh
set -e

# Runtime config generation (NFR Design pattern): writes API_BASE_URL, read from the
# container's environment at startup, into a static config.js served alongside
# index.html -- so the same built image works regardless of what URL the API Service
# ends up at, no rebuild needed.
#
# Addendum (2026-08-02): API_BASE_URL is left unset (empty string) here unless the
# operator explicitly provided one -- no more hardcoded "http://localhost:7878"
# fallback. src/config.ts derives the correct address at runtime, in the browser,
# from whatever host the page was actually loaded from -- a fixed server-side
# fallback baked the same "localhost" into every client regardless of how THEY
# reached the app, which broke API calls entirely for anyone accessing via a LAN IP.
#
# Addendum (2026-08-22, Kubernetes Ingress support): API_BASE_PATH is for a single
# reverse-proxy/Ingress fronting both frontend and API on ONE host (e.g. "/api"
# routed to api-service) -- unlike API_BASE_URL, it deliberately carries no scheme
# or host of its own, so src/config.ts can combine it with whatever origin the page
# was ACTUALLY loaded through (window.location.origin). A fixed scheme+host baked in
# at deploy time (what API_BASE_URL does) broke the moment the same Ingress host was
# reachable both as OrbStack's auto-upgraded HTTPS (the host machine) and as plain
# HTTP (another device on the LAN, via a hosts-file entry, with no way to trust
# OrbStack's local-only cert) -- found live, testing from a second device.
cat > /usr/share/nginx/html/config.js <<EOF
window.__APP_CONFIG__ = { apiBaseUrl: "${API_BASE_URL:-}", apiBasePath: "${API_BASE_PATH:-}" };
EOF

exec nginx -g "daemon off;"
