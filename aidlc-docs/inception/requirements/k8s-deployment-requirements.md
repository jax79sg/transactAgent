# Kubernetes Deployment Support — Requirements

## Intent Analysis Summary

- **User Request**: GitHub issue #2 ("Support for deployment into K8S") — "Make this a scalable deployment on K8S please."
- **Request Type**: New Feature (Infrastructure/Deployment)
- **Scope Estimate**: System-wide — a new deployment path for all 5 existing runtime services (`database`, `api-service`, `ingestion-worker`, `frontend`, `vector-db`), plus two new pieces of cluster-shared infrastructure (External Secrets Operator, HashiCorp Vault). No application code changes to any unit.
- **Complexity Estimate**: Complex — spans every unit's deployment topology at once, introduces a real secrets-management architecture (Vault in persistent mode, with manual unseal), and has several genuine constraints specific to this app (a correctness-sensitive singleton `ingestion-worker`, a host-only oMLX dependency, an explicitly single-user app being asked to be "scalable").

## Functional Requirements

- **FR-K8S-1**: Provide a Helm chart deploying all 5 existing runtime services as Kubernetes workloads: `database` (Postgres), `api-service`, `ingestion-worker`, `frontend`, `vector-db` (Qdrant).
- **FR-K8S-2**: The chart's manifests are provider-agnostic — no cloud-specific resource types or assumptions (no cloud `LoadBalancer`, no hardcoded cloud `StorageClass` name) — while being deployable and verifiable against the user's local OrbStack Kubernetes cluster today.
- **FR-K8S-3**: `api-service` and `frontend` (stateless, safely replicable) support a `HorizontalPodAutoscaler`. `database`, `ingestion-worker`, and `vector-db` (stateful and/or singleton by design) are fixed at a single replica with no HPA — this is a correctness constraint for `ingestion-worker` specifically (its poll loop has no leader-election or concurrency-safety design; a second concurrent replica would double-process ingestion runs), not just a resource-efficiency choice.
- **FR-K8S-4**: `database` and `vector-db` use `PersistentVolumeClaim`s against the cluster's default `StorageClass` (no cluster-specific storage assumptions).
- **FR-K8S-5**: Secrets (`JWT_SECRET`, `GEMINI_API_KEY`, `OPENROUTER_*` credentials, `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET`, `DB_PASSWORD`) are sourced into the cluster via `ExternalSecret` resources (External Secrets Operator) backed by a HashiCorp Vault instance. Both ESO and Vault are cluster-shared prerequisite infrastructure, explicitly **not** part of this app's Helm chart — the chart only defines the `ExternalSecret`/`SecretStore` objects that consume them.
- **FR-K8S-6**: Provide setup material (Helm values / manifests, not necessarily executed by this feature) for installing ESO and a Vault instance in persistent mode (Raft storage, not dev/in-memory), each in their own namespace.
- **FR-K8S-7**: Provide a helper script that reads the project's existing `.env` file and writes each secret value into Vault via `vault kv put`, run once per environment — not part of the Helm chart, not run automatically by it.
- **FR-K8S-8**: Expose the app externally via a Kubernetes `Ingress`, using OrbStack's automatic `*.orb.local` hostname + locally-trusted HTTPS (no public domain, no cert-manager dependency for the primary target environment).
- **FR-K8S-9**: Each service's container gets liveness/readiness probes reusing its existing health signal where one exists (`api-service`'s `/health`; `ingestion-worker`'s existing file-based heartbeat mechanism; `database`'s `pg_isready`; `frontend`'s static-file serving).
- **FR-K8S-10**: `docker-compose.yml` remains unchanged and continues to work for local dev — Kubernetes is an additional deployment option, not a replacement.
- **FR-K8S-11**: `EMBEDDING_BASE_URL` (the host-only oMLX server) is reached from the cluster exactly as it is today — as an external URL the `ingestion-worker`/`api-service` call out to over the network, relying on the existing no-retry/soft-fail graceful-degradation behavior if it's unreachable. No new K8s-specific networking is introduced for this.
- **FR-K8S-12**: `model-training/` (host-only, macOS/Metal-dependent, no existing container at all) is explicitly out of scope for this feature.
- **FR-K8S-13**: Image build/push to a registry is explicitly out of scope — the chart assumes pre-built images already exist wherever `values.yaml` points (image repository/tag are chart values, not hardcoded).

## Non-Functional Requirements

- **NFR-K8S-1 (Portability)**: No cloud-provider-specific Kubernetes resources or assumptions anywhere in the chart, beyond the OrbStack-specific Ingress/TLS convenience noted in FR-K8S-8 (which is isolated to Ingress annotations, not the rest of the chart).
- **NFR-K8S-2 (Secret Hygiene)**: No secret value — nor Vault unseal keys/root token — ever appears in plaintext in the Helm chart, any values file, any script output committed to git, or git history. Vault's unseal material is generated at init time and handed to the user out-of-band (e.g. printed to the terminal once); it is the user's responsibility to store it securely.
- **NFR-K8S-3 (No Live Changes This Session)**: Per explicit user instruction, nothing described here is installed or applied to the user's real running OrbStack cluster by Claude during this feature's work. Deliverables are the Helm chart, ESO/Vault setup material, and the secret-population script — verification is via `helm lint` and `helm template` (dry-run rendering) and schema/manifest validation, not a real `helm install`/`kubectl apply` against the live cluster.
- **NFR-K8S-4 (Resource Discipline)**: Every container in the chart declares resource `requests`/`limits` — "production-grade" per the user's own framing of "scalable," not just "runs."
- **NFR-K8S-5 (Replica Safety)**: `ingestion-worker`, `database`, and `vector-db` must be structurally prevented from running with more than one replica (fixed `replicas: 1`, no HPA object generated for them, regardless of values overrides) — this is a correctness guarantee, not a default that a values override could accidentally violate.
- **NFR-K8S-6 (Chart Configurability)**: Replica counts (where applicable), resource limits, image repository/tag, Ingress hostname, and storage sizes are all `values.yaml`-configurable, not hardcoded into templates.

## Key Design Resolution (found during requirements analysis, not a new question)

The frontend currently derives its API URL at runtime as `${window.location.hostname}:7878` (`config.ts`'s `sameHostApiBaseUrl()`), which assumes the browser can reach the API on a distinct port directly — true in Docker Compose (both ports published on the same host) but not naturally true behind a single Kubernetes `Ingress` (one hostname, port 80/443, path-based routing to internal Services). Resolution: the Helm chart's frontend deployment sets `API_BASE_URL` explicitly via the existing runtime-config override mechanism (`window.__APP_CONFIG__`/`config.js`, already designed for exactly this kind of environment-specific override — see `frontend/src/config.ts`) to an Ingress path like `https://<host>/api`, with the Ingress routing `/api` to `api-service` and `/` to `frontend`. No frontend code changes are needed — this is a deployment-time configuration decision, to be finalized in Infrastructure Design.

## Answers to Clarifying Questions (source of truth)

| # | Question (short) | Answer |
|---|---|---|
| 1 | What "scalable" means | C — Both production-grade orchestration and real HPA on api-service/frontend |
| 2 | Target cluster | Other — OrbStack (local), manifests must stay provider-agnostic |
| 3 | Deliverable format | A — Helm chart |
| 4 | Secrets mechanism | Other — External Secrets Operator + HashiCorp Vault, both cluster-shared, not part of the chart |
| 5 | Persistent storage | A — cluster's default StorageClass |
| 6 | External access | A — Ingress (but no public domain available) |
| 7 | Image source | A — pre-built images assumed, build/push out of scope |
| 8 | Docker Compose | A — keep it for local dev |
| 9 | oMLX reachability | A — external URL, cluster calls out, no special networking |
| C1 | Vault mode | B — persistent storage (Raft), not dev mode |
| C2 | Vault population | A — helper script reading `.env`, run manually per environment |
| C3 | Ingress TLS w/ no domain | A — OrbStack's automatic `*.orb.local` HTTPS |
| C4 | Live install this session | B — No; produce artifacts only, user applies them |

## Summary

Deliver a provider-agnostic Helm chart deploying all 5 existing services to Kubernetes, sized for "scalable" as production-grade orchestration plus real HPA on the two safely-replicable services (`api-service`, `frontend`) — `database`/`ingestion-worker`/`vector-db` stay single-replica by hard constraint, not just default, since `ingestion-worker`'s poll loop isn't concurrency-safe. Secrets flow through the External Secrets Operator from a persistent-mode HashiCorp Vault, both installed as cluster-shared prerequisites outside the chart, populated via a one-time helper script reading the existing `.env`. External access is via Ingress using OrbStack's automatic local HTTPS. `model-training/` and the host-only oMLX dependency are explicitly out of scope / unchanged. Per explicit user instruction, nothing is installed live on the user's real cluster during this work — deliverables are validated via `helm lint`/`helm template`, not a real deployment.
