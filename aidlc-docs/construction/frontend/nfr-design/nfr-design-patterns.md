# NFR Design Patterns — Unit 4: Frontend SPA

## Pattern: Runtime Config File

**Category**: Logical Components (resolves Question 1 = B)

At container startup, an entrypoint script reads `API_BASE_URL` from the environment and writes it into a small `config.js` file served alongside `index.html` (e.g., `window.__APP_CONFIG__ = { apiBaseUrl: "..." }`), loaded via a `<script>` tag in `index.html` *before* the main app bundle. The React app reads `window.__APP_CONFIG__.apiBaseUrl` at startup rather than a Vite build-time `import.meta.env` variable. This means the same built Docker image works regardless of what port/host the API Service ends up on — only the container's environment variable needs to change, no rebuild.

## Pattern: React Error Boundary

A top-level error boundary wraps the routed app content, catching rendering errors and showing a generic "Something went wrong" fallback with a reload option, instead of an unstyled blank page.

## Pattern: Loading/Skeleton States

Every TanStack Query-backed component (`DashboardPage` tabs, `TransactionTable`, `RunHistoryTable`, etc.) uses TanStack Query's `isPending`/`isFetching` states to show a skeleton placeholder or subtle loading indicator rather than a layout-shifting blank state.

## N/A Categories (justified)

- **Scalability/Performance Patterns**: N/A — single personal user; Vite's default production build (code splitting, minification, tree-shaking) is sufficient without further tuning
- **Additional Security Patterns**: N/A beyond what's already decided (sessionStorage JWT)
