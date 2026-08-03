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
cat > /usr/share/nginx/html/config.js <<EOF
window.__APP_CONFIG__ = { apiBaseUrl: "${API_BASE_URL:-}" };
EOF

exec nginx -g "daemon off;"
