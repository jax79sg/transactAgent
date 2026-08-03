# NFR Design Plan — Unit 4: Frontend SPA

**Input**: `aidlc-docs/construction/frontend/nfr-requirements/` (approved)

## NFR Design Category Assessment

| Category | Assessment |
|---|---|
| Resilience Patterns | React error boundary around the app shell (catches rendering errors, shows a fallback instead of a blank white screen) — decided directly, standard React practice |
| Scalability Patterns | N/A — single personal user |
| Performance Patterns | N/A beyond Vite's default production build optimizations (code splitting, minification) — no further tuning needed at this scale |
| Security Patterns | JWT in `sessionStorage` (already decided); no additional pattern |
| Logical Components | Centralized API client module (decided in NFR Requirements); loading/skeleton state pattern for async data (decided directly, standard TanStack Query + component practice). **Real decision**: how the frontend knows the API's base URL — question below |

## Execution Checklist

- [x] Step 1: Resolve clarifying question below (API base URL configuration strategy) — Answer: B, runtime config file
- [x] Step 2: Generate `nfr-design-patterns.md`
- [x] Step 3: Generate `logical-components.md`

## Clarifying Question

### Question 1 — API Base URL Configuration
A Vite production build is static files (HTML/JS/CSS) served by a container — but that build needs to know the API Service's URL (`http://localhost:7878` per Unit 2's Infrastructure Design). How should this be configured?

A) **Build-time env var** (`VITE_API_BASE_URL`, baked into the JS bundle at `docker build` time via a build arg) — simplest, but changing the API URL later requires rebuilding the frontend image

B) **Runtime config file** — a small `config.js` (or similar) fetched by the app on load, generated from an environment variable when the container *starts* (not when the image is *built*) — the same built image works regardless of what URL the API ends up at, no rebuild needed if the API's address changes later

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

**Instructions**: Fill in the `[Answer]:` tag above, then let me know when you're done.
