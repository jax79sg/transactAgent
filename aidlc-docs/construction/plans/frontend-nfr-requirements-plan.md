# NFR Requirements Plan — Unit 4: Frontend SPA

**Input**: `aidlc-docs/construction/frontend/functional-design/` (approved)

## NFR Category Assessment

| Category | Assessment |
|---|---|
| Scalability | N/A — single personal user |
| Performance | No hard target; "rich UI" (NFR-3.1) is a UX requirement, addressed via the component library choice (Question 2) rather than a performance target |
| Availability | N/A — Resiliency Baseline extension opted out |
| Security | JWT in `sessionStorage` (Functional Design Question 1); no additional pattern — Security Baseline extension opted out |
| Tech Stack Selection | **Real decisions**: framework (Question 1), UI component/styling library (Question 2), charting library (Question 3). Build tool, routing, data-fetching, and test framework decided directly below. |
| Reliability | Covered by business-logic-model.md's polling-recovery and centralized-401-handling patterns |
| Maintainability | PBT framework: **fast-check** (the TypeScript/JavaScript equivalent of Hypothesis, per `property-based-testing.md`'s own recommendation table), applied to the filter-state <-> URL-query-string round-trip function (business-logic-model.md) — the clearest pure, round-trippable function in this unit (Partial PBT mode) |
| Usability | NFR-3.1 "rich UI" — addressed by Question 2 (component library choice) |

## Direct Decisions (no user tradeoff, documented for transparency)

- **Language**: TypeScript (not plain JavaScript) — type safety matching the DTOs already defined in Unit 2's `domain-entities.md`
- **Build tool**: Vite — standard modern tooling, fast dev server, pairs with any of the frameworks in Question 1
- **Routing**: framework-appropriate standard router (e.g., React Router if React is chosen)
- **Data fetching / server state**: TanStack Query (or framework-equivalent) — handles the run-status polling lifecycle (business-logic-model.md) and category-list caching cleanly via its built-in refetch-interval and cache-invalidation primitives, rather than hand-rolled polling loops
- **HTTP client**: native `fetch` — no need for axios given TanStack Query already handles retries/caching
- **Test framework**: Vitest + Testing Library (framework-appropriate variant) + fast-check

## Execution Checklist

- [x] Step 1: Resolve clarifying questions below (framework, component/styling library, charting library) — React, Tailwind+Radix, Chart.js
- [x] Step 2: Generate `nfr-requirements.md`
- [x] Step 3: Generate `tech-stack-decisions.md`

## Clarifying Questions

### Question 1 — Frontend Framework
Requirements Analysis floated "React" as an illustrative example only. Confirming now:

A) **React** — largest ecosystem, most third-party component/chart library choices, matches the example already floated

B) **Vue** — gentler learning curve, excellent tooling, smaller ecosystem than React but still very mature

C) **Svelte** — least boilerplate, compiles away most of the framework at build time, smallest ecosystem of the three

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 2 — UI Component / Styling Library
This directly shapes how "rich" the UI feels (NFR-3.1).

A) **Tailwind CSS + a headless/unstyled component set** (e.g., Radix/shadcn-style) — full visual control, modern look, more upfront styling work per component

B) **A complete component library** (e.g., MUI, Ant Design, or the framework's most popular equivalent) — fast to build with, consistent polished look out of the box, less visual customization

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 3 — Charting Library
For the 3 dashboard visualizations (category trends, cash flow, bank breakdown).

A) **Recharts** (or the chosen framework's equivalent, e.g. `vue-chartjs`) — declarative, component-based charts, good fit for a component-driven app, moderate customization

B) **Chart.js** (via a thin wrapper) — canvas-based, very common, slightly more imperative API, broad chart-type support

C) **A more powerful/lower-level library** (e.g., D3, Observable Plot) — maximum control and customization, steeper learning curve, more code to write per chart

X) Other (please describe after [Answer]: tag below)

[Answer]:B

---

**Instructions**: Fill in each `[Answer]:` tag above, then let me know when you're done.
