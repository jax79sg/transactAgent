# NFR Requirements — Unit 4: Frontend SPA

## Assessed Categories

| Category | Requirement | Rationale |
|---|---|---|
| Scalability | No target | Single personal user |
| Performance | No hard target; addressed via component library choice | NFR-3.1 "rich UI" is a UX concern, not a perf-budget concern at this scale |
| Availability | No SLA | Resiliency Baseline extension opted out |
| Security | JWT in `sessionStorage`; no additional pattern | Security Baseline extension opted out |
| Reliability | Polling-recovery (409 handling) and centralized 401-handling | Already captured in Functional Design |
| Maintainability | PBT framework: **fast-check**, applied to the filter-state <-> URL-query-string round-trip function | Partial PBT mode (requirements.md NFR-5.2) |
| Usability | NFR-3.1 addressed via Tailwind + headless components (Question 2 = A) | Full visual control for a genuinely "rich" feel |

## Tech Stack Decisions (Summary — see tech-stack-decisions.md)

- **Framework**: React (Question 1 = A)
- **Styling**: Tailwind CSS + Radix UI primitives (Question 2 = A)
- **Charts**: Chart.js via `react-chartjs-2` (Question 3 = B)
- **Language**: TypeScript
- **Build tool**: Vite
- **Data fetching**: TanStack Query
- **Routing**: React Router
- **PBT**: fast-check
