# Logical Components — Kubernetes Deployment Support

## Cluster-Shared Prerequisites (outside this feature's Helm chart)
| Component | Namespace | Purpose |
|---|---|---|
| External Secrets Operator | `external-secrets` | Watches `ExternalSecret` objects across the cluster, syncs values from Vault into native `Secret` objects. |
| HashiCorp Vault | `vault` | Source of truth for all real secret values; single-node, Raft/persistent storage. |
| ingress-nginx | `ingress-nginx` | Ingress controller — no `Ingress` resource does anything without one; confirmed absent on the target cluster, so setup material is included. |

## This App's Helm Chart (`deploy/helm/transactagent/`) — objects in the `transactagent` namespace
| Object | Kind | Notes |
|---|---|---|
| `database` | `StatefulSet` + `Service` (headless-not-required, ClusterIP) + `PersistentVolumeClaim` | Postgres. 1 replica, fixed. |
| `vector-db` | `StatefulSet` + `Service` (ClusterIP) + `PersistentVolumeClaim` | Qdrant. 1 replica, fixed. |
| `api-service` | `Deployment` + `Service` (ClusterIP) + `HorizontalPodAutoscaler` | 1–3 replicas. |
| `frontend` | `Deployment` + `Service` (ClusterIP) + `HorizontalPodAutoscaler` | 1–3 replicas. |
| `ingestion-worker` | `Deployment` (no `Service` — nothing calls it) | 1 replica, hardcoded in the template. |
| App config | `ConfigMap` | All non-secret environment variables (the ~40 tunables already in `docker-compose.yml`/`.env.example`). |
| App secrets | `ExternalSecret` (× however many logical secret groups — likely one per consuming service, or one shared, decided during Code Generation) | Populated by ESO from Vault; consumed by pods via `envFrom` on the resulting `Secret`. |
| External access | `Ingress` | `/` → `frontend`, `/api` → `api-service`; `ingressClassName: nginx`. |
| Data-layer hardening | `NetworkPolicy` (× 2 — `database`, `vector-db`) | Ingress restricted to the app's own namespace. |
| Namespace | `Namespace` | `transactagent` (or `values.yaml`-configured name) — the chart can create it or assume it exists, decided during Code Generation. |

## Supporting Artifacts (not Kubernetes objects)
| Artifact | Location | Purpose |
|---|---|---|
| Secret population script | `deploy/scripts/populate-vault-secrets.sh` | One-time, manually-run script reading `.env` and writing each value into Vault via `vault kv put` (FR-K8S-7). |
| Prerequisite setup docs/values | `deploy/helm/prerequisites/` | Values files + install instructions for ESO, Vault, and ingress-nginx (their official upstream Helm charts — not maintained by this project). |
| Chart README | `deploy/helm/transactagent/README.md` | End-to-end deploy instructions: install prerequisites → init/unseal Vault → populate secrets → `helm install`. |
