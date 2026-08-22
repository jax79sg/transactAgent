# Tech Stack Decisions — Kubernetes Deployment Support

## Chart Tooling
- **Helm 3** (`apiVersion: v2` chart) — per Q3=A. No chart dependencies on other charts; ESO and Vault are separate, cluster-shared installs (FR-K8S-5/6), not chart dependencies.
- **Kubernetes API versions targeted**: `apps/v1` (Deployment/StatefulSet), `autoscaling/v2` (HPA), `networking.k8s.io/v1` (Ingress), `v1` (Service/PVC/ConfigMap). All stable since Kubernetes 1.23+ — safely below OrbStack's current `v1.35.6`, and a reasonable generic floor for "provider-agnostic" (NFR-K8S-1).

## Workload Types
| Service | Kind | Why |
|---|---|---|
| `database` (Postgres) | `StatefulSet` | Stable identity + PVC is the idiomatic pattern for a singleton stateful service. |
| `vector-db` (Qdrant) | `StatefulSet` | Same reasoning — singleton, PVC-backed. |
| `api-service` | `Deployment` | Stateless, HPA-managed (min 1 / max 3). |
| `frontend` | `Deployment` | Stateless, HPA-managed (min 1 / max 3). |
| `ingestion-worker` | `Deployment`, hardcoded `replicas: 1` | Not exposed via a Service (nothing calls it — it's a poll loop, like today's Compose setup) — no data of its own to persist (writes go to `database`), so `StatefulSet` isn't needed, but `replicas` is deliberately not a `values.yaml`-exposed field (NFR-K8S-5 — structural, not a default). |

## Probe Strategy (reusing each service's existing Docker Compose healthcheck)
| Service | Probe type | Command / path |
|---|---|---|
| `database` | exec | `pg_isready -U $DB_USER -d $DB_NAME` (identical to today's healthcheck) |
| `api-service` | httpGet | `GET /health` on container port 8000 |
| `ingestion-worker` | exec (liveness only — no readiness needed, nothing routes traffic to it) | `find /tmp/worker-heartbeat -mmin -0.5` (heartbeat file touched within the last 30s) |
| `vector-db` | tcpSocket | port 6333 (Qdrant's image has neither `curl` nor `wget`, confirmed during the original Infrastructure Design — a raw TCP check is what Compose already does via `/dev/tcp`) |
| `frontend` | httpGet | `GET /` on container port 80 |

## Secrets: External Secrets Operator + HashiCorp Vault
- **ESO**: official `external-secrets/external-secrets` Helm chart, installed in its own `external-secrets` namespace — cluster-shared prerequisite, not part of this app's chart (FR-K8S-5).
- **Vault**: official `hashicorp/vault` Helm chart, installed in its own `vault` namespace — cluster-shared prerequisite. `server.ha.enabled=false` (single node — the user asked for persistent storage via C1=B, not a full multi-node HA cluster, which would be a much bigger and unrequested jump), `server.dataStorage.enabled=true` (Raft integrated storage, not `dev` mode).
- **Vault init/unseal**: standard `vault operator init` (5 key shares / 3 threshold, Vault's default Shamir's Secret Sharing) — a one-time manual step for whoever deploys; keys are their responsibility, never touched by this project's chart or scripts (NFR-K8S-2).
- **ESO↔Vault auth**: Vault's Kubernetes auth method — a Vault policy scoped to read the app's secret path, bound to a Kubernetes auth role that trusts ESO's ServiceAccount token. No static Vault token stored anywhere (more secure than the alternative, and it's the standard pattern for in-cluster ESO).
- **Secret path convention**: Vault KV v2 engine, paths under `secret/transactagent/<key>` (e.g. `secret/transactagent/jwt-secret`). The chart's `ExternalSecret` resources reference these paths; the actual write into Vault is FR-K8S-7's helper script, run manually per environment.

## Ingress
- **Controller**: no Ingress controller currently exists on the user's OrbStack cluster (confirmed live via a read-only `kubectl get ingressclass`/`kubectl get pods -A` check — see `k8s-deployment-nfr-requirements-plan.md`). Per Q2's answer, include `ingress-nginx` setup material (official `ingress-nginx/ingress-nginx` Helm chart) as prerequisite documentation — not installed by this feature, per the user's explicit choice not to have live cluster changes made this session.
- **TLS/hostname**: `ingressClassName: nginx`; hostname defaults to an OrbStack-style `transactagent.k8s.orb.local` in `values.yaml` (adjustable — OrbStack auto-provisions a locally-trusted HTTPS cert for exposed LoadBalancer/Ingress hostnames on this pattern, per C3=A; the user should confirm the exact hostname OrbStack assigns once `ingress-nginx`'s Service is actually running, since this can only be observed after that controller exists — the chart makes it a one-line values.yaml change either way).
- **Routing**: `/` → `frontend` Service (port 80); `/api` → `api-service` Service (port 8000) — resolves the frontend's runtime `API_BASE_URL` derivation problem identified in Requirements (`k8s-deployment-requirements.md`'s "Key Design Resolution") by setting `frontend`'s `API_BASE_URL` env var to `https://<ingress-host>/api` via the chart's values, using the existing runtime-config override mechanism — no frontend code change.

## Resource Requests/Limits (NFR-K8S-4 — "production-grade," per the user's own framing)
| Service | CPU request | CPU limit | Memory request | Memory limit |
|---|---|---|---|---|
| `database` | 250m | 1 | 256Mi | 1Gi |
| `vector-db` | 200m | 1 | 256Mi | 1Gi |
| `api-service` | 100m | 500m | 128Mi | 512Mi |
| `ingestion-worker` | 100m | 500m | 128Mi | 512Mi |
| `frontend` | 50m | 200m | 64Mi | 128Mi |

All `values.yaml`-configurable (NFR-K8S-6) — these are sensible starting points for a single-user workload, not measured production benchmarks, and documented as such in the chart's README.

## Persistent Storage
- `database` and `vector-db` each get a `PersistentVolumeClaim` using the cluster's default `StorageClass` (no `storageClassName` set — Q5=A) — 5Gi default for `database`, 2Gi default for `vector-db`, both `values.yaml`-configurable.
