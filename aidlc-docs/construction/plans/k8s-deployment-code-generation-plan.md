# Code Generation Plan — Kubernetes Deployment Support

**Scope**: Cross-cutting (all 5 existing services' deployment topology) — not tied to one existing unit's directory.
**Workspace root**: `/Users/jax/projects/transactAgent`
**Application code location**: `deploy/` (new top-level directory — brownfield repo, but no existing K8s/Helm structure to extend)
**Requirements implemented**: FR-K8S-1..13, NFR-K8S-1..6 (`k8s-deployment-requirements.md`)
**Design inputs**: `nfr-design-patterns.md`, `logical-components.md`, `infrastructure-design.md`, `deployment-architecture.md`

## Steps

- [ ] **Step 1 — Chart scaffold**: `deploy/helm/transactagent/Chart.yaml`, `deploy/helm/transactagent/values.yaml` (full schema per `infrastructure-design.md`, including the ~44 non-secret env vars as a flat `env:` map and the 6 secret keys' Vault-path list).

- [ ] **Step 2 — Namespace + config**: `templates/namespace.yaml`, `templates/configmap.yaml` (iterates `.Values.env`, no per-key template duplication).

- [ ] **Step 3 — Secrets bridge**: `templates/externalsecret.yaml` — `SecretStore` (Kubernetes-auth-backed, pointing at the prerequisite Vault) + `ExternalSecret` (syncs the 6 secret keys from `secret/transactagent/*` into one native `Secret`).

- [ ] **Step 4 — Database (Postgres)**: `templates/database-statefulset.yaml`, `templates/database-service.yaml`, `templates/database-pvc.yaml`, `templates/database-networkpolicy.yaml`. Probe: `pg_isready`. Fixed 1 replica.

- [ ] **Step 5 — Vector DB (Qdrant)**: `templates/vector-db-statefulset.yaml`, `templates/vector-db-service.yaml`, `templates/vector-db-pvc.yaml`, `templates/vector-db-networkpolicy.yaml`. Probe: TCP 6333. Fixed 1 replica.

- [ ] **Step 6 — API Service**: `templates/api-service-deployment.yaml`, `templates/api-service-service.yaml`, `templates/api-service-hpa.yaml`. Probe: `GET /health`. HPA 1-3 @ 80% CPU.

- [ ] **Step 7 — Frontend**: `templates/frontend-deployment.yaml`, `templates/frontend-service.yaml`, `templates/frontend-hpa.yaml`. Probe: `GET /`. HPA 1-3 @ 80% CPU. `API_BASE_URL` env var set to the Ingress host's `/api` path (resolves the frontend design note).

- [ ] **Step 8 — Ingestion Worker**: `templates/ingestion-worker-deployment.yaml` (no Service). Probe: exec heartbeat-file check. `replicas: 1` hardcoded in the template, not sourced from `values.yaml` (NFR-K8S-5 — structural enforcement).

- [ ] **Step 9 — Ingress**: `templates/ingress.yaml` — `ingressClassName: nginx`, `/` → frontend, `/api` → api-service.

- [ ] **Step 10 — Chart README**: `deploy/helm/transactagent/README.md` — end-to-end deploy instructions (prerequisites → Vault init/unseal → populate secrets → `helm install`), values reference table.

- [ ] **Step 11 — Prerequisite setup material**: `deploy/helm/prerequisites/README.md` + `ingress-nginx-values.yaml` + `vault-values.yaml` + `external-secrets-values.yaml` — install commands and values for the 3 cluster-shared components, plus the manual Vault init/unseal/policy/auth-role/SecretStore steps.

- [ ] **Step 12 — Secret population script**: `deploy/scripts/populate-vault-secrets.sh` — reads `.env`, writes the 6 secret keys into Vault via `vault kv put`.

- [ ] **Step 13 — Documentation summary**: `aidlc-docs/construction/k8s-deployment/code/k8s-deployment-code-summary.md`.

## Story/Requirement Traceability
| Step | Requirements Covered |
|---|---|
| 1–3 | FR-K8S-1, FR-K8S-5, FR-K8S-6, FR-K8S-7, NFR-K8S-2, NFR-K8S-6 |
| 4–5 | FR-K8S-4, NFR-K8S-5 |
| 6–7 | FR-K8S-3, FR-K8S-9, FR-K8S-13 (Key Design Resolution) |
| 8 | FR-K8S-3, NFR-K8S-5 |
| 9 | FR-K8S-8 |
| 10–11 | FR-K8S-6, NFR-K8S-2 |
| 12 | FR-K8S-7 |
| 13 | — (documentation) |
