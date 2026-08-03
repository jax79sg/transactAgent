# Tech Stack Decisions — Unit 4: Frontend SPA

| Decision | Choice | Rationale |
|---|---|---|
| Framework | **React 18+** | Question 1 = A |
| Language | **TypeScript** | Type safety matching Unit 2's DTOs |
| Build tool | **Vite** | Fast dev server, standard modern React tooling |
| Styling | **Tailwind CSS** | Question 2 = A |
| Component primitives | **Radix UI** (unstyled/headless) | Question 2 = A's "headless/unstyled component set" — accessible primitives (dialogs, dropdowns, selects) styled with Tailwind |
| Charts | **Chart.js** via **react-chartjs-2** | Question 3 = B |
| Routing | **React Router** | Standard React routing |
| Server state / data fetching | **TanStack Query** | Handles polling (`refetchInterval`), caching, and invalidation declaratively — fits the run-status polling and category-cache patterns in `business-logic-model.md` directly |
| HTTP client | Native `fetch`, wrapped in a single API client module (handles `Authorization` header injection and centralized 401 handling) | No axios needed given TanStack Query |
| Test framework | **Vitest** + **React Testing Library** + **fast-check** | Vitest pairs natively with Vite; RTL for component tests; fast-check for the PBT round-trip test |
| PBT framework | **fast-check** | JS/TS equivalent of Hypothesis, applied to the filter-state <-> URL round-trip (Partial PBT mode) |

## Package Dependency on Unit 2 (not Unit 1)

Unlike Units 2/3, Unit 4 has **no** dependency on the `database` package — it only ever talks to Unit 2's REST API (per `unit-of-work-dependency.md`).
