# NFR Requirements — Kubernetes Deployment Support

## Scalability
- `api-service` and `frontend`: `HorizontalPodAutoscaler`, min 1 / max 3 replicas, scale on 80% average CPU utilization (Q1=A — conservative; this is a single-user app, so HPA exists for resilience/rolling-update headroom, not real traffic scaling).
- `database`, `ingestion-worker`, `vector-db`: hard-fixed at 1 replica, no HPA (NFR-K8S-5 — a correctness constraint for `ingestion-worker` specifically, and the natural shape for the other two as singleton stateful services).

## Performance
- No new performance requirement beyond what each service already meets today — this feature changes where the containers run, not what they do.
- Resource `requests` sized for normal operation, `limits` sized with headroom for occasional bursts (e.g. `ingestion-worker` during an active ingestion run, `api-service` during a CSV export) — see `tech-stack-decisions.md` for exact values.

## Availability
- Liveness/readiness probes reuse each service's existing health signal (see `tech-stack-decisions.md` — Probe Strategy) so a hung/unhealthy pod is detected and restarted the same way Docker Compose's `healthcheck:` + `restart: unless-stopped` already does today.
- No multi-region/disaster-recovery requirement — matches this app's existing single-host operational model; Kubernetes here is about orchestration quality (auto-restart, rolling updates), not geographic redundancy.

## Security
- No secret value (API keys, JWT secret, DB password) or Vault unseal material appears in the Helm chart, any values file, any script, or git history (NFR-K8S-2) — secrets flow app-side only as `ExternalSecret` → `Secret` references.
- ESO authenticates to Vault via Vault's Kubernetes auth method (a scoped Vault policy bound to ESO's ServiceAccount token) — no long-lived static Vault token stored anywhere.
- Vault runs in persistent (Raft) mode per the user's explicit choice (C1=B); initial unseal uses Vault's standard Shamir's Secret Sharing (5 key shares / 3 threshold) — the keys are generated once, shown to whoever runs `vault operator init`, and are that person's responsibility to store securely (e.g. a password manager) — this project never sees or stores them.

## Tech Stack Selection
See `tech-stack-decisions.md` for the full list with rationale (Helm, External Secrets Operator, HashiCorp Vault, ingress-nginx, StatefulSet vs. Deployment choices, probe reuse, resource sizing, Kubernetes API versions).

## Reliability
- `ingestion-worker`'s replica-safety constraint (NFR-K8S-5) is enforced structurally in the chart template (no `replicas` value exposed for it in `values.yaml` — it's hardcoded in the template), not just documented, so a values override can't accidentally violate it.
- Rolling updates on `api-service`/`frontend` (the two HPA-managed services) use Kubernetes' default `RollingUpdate` strategy — no custom deployment strategy needed.

## Maintainability
- All environment-specific values (image tag, ingress host, replica bounds, resource sizes, storage sizes) live in `values.yaml`, not hardcoded in templates — a future environment (a second cluster, a staging environment) only needs a new values file, not template edits.
- `docker-compose.yml` remains the primary local-dev path, unchanged (FR-K8S-10) — no dual-maintenance burden on day-to-day development.

## Usability
- N/A — no end-user-facing interface; this is an operator/deployer-facing feature. Usability here means the deploying person (the project owner) can `helm install` and get a working system with clear, documented prerequisites.
