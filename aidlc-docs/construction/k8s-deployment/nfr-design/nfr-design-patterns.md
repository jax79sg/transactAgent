# NFR Design Patterns — Kubernetes Deployment Support

## Resilience Patterns
- **Probe-driven self-healing**: every workload gets a `livenessProbe` matching its existing Docker Compose healthcheck (see `tech-stack-decisions.md`'s Probe Strategy table) — an unhealthy pod is killed and restarted by Kubernetes' own controller loop, the direct K8s equivalent of Compose's `restart: unless-stopped` + `healthcheck:`.
- **Readiness gates traffic, not restarts**: `api-service` and `frontend` additionally get a `readinessProbe` (same check as their liveness probe) so their `Service`/HPA-managed `Deployment` never routes traffic to a pod that isn't actually ready yet — relevant now that they can have >1 replica, unlike today's single-container Compose setup.
- **No PodDisruptionBudget**: deliberately omitted. With `minReplicas: 1` on the HPA-managed services and a single-user, non-critical-uptime app, a PDB would add operational complexity (it can block voluntary node drains) without a real corresponding benefit here. Documented as a conscious omission, not an oversight, in case a future multi-node/HA requirement changes the calculus.

## Scalability Patterns
- **HPA on stateless services only**: `api-service`/`frontend` scale 1→3 replicas on 80% average CPU (per NFR Requirements). `database`/`vector-db`/`ingestion-worker` are structurally single-replica — no HPA object is even generated for them, not just "HPA with max=1."

## Performance Patterns
- No new caching/queueing layer introduced — this feature changes deployment topology only, not the request/processing path each service already uses.
- Resource `requests` set close to steady-state usage so the scheduler makes reasonable bin-packing decisions; `limits` set with headroom for known bursty operations (an active ingestion run, a large CSV export) rather than being equal to `requests` (which would throttle those bursts unnecessarily).

## Security Patterns
- **Secrets never touch the chart**: `ExternalSecret` objects are the only secret-related resource the chart defines — the actual values live in Vault, synced into native `Secret` objects by ESO at runtime, and referenced by pods via `envFrom`. This means `helm template`'s output (and anything committed to git) never contains a real secret value, by construction, not by convention.
- **Least-privilege Vault access**: ESO's Vault policy is scoped to read-only access under `secret/transactagent/*` — it cannot read or write anything outside this app's own secret path, even though it shares the same Vault instance as (potentially) other apps on the cluster.
- **NetworkPolicy restricting the data layer**: `database` and `vector-db` each get a `NetworkPolicy` allowing ingress only from pods within the app's own namespace (rather than being reachable from anywhere in the cluster) — a straightforward, low-maintenance hardening step consistent with "production-grade" (NFR-K8S-4), without requiring a service mesh or anything heavier.
- **Dedicated namespace**: all 5 app services, plus their `ConfigMap`/`Secret`/`PVC`/`NetworkPolicy` objects, live in one dedicated namespace (default `transactagent`, `values.yaml`-configurable) — separate from the `external-secrets`, `vault`, and `ingress-nginx` namespaces housing the cluster-shared prerequisites.

## Logical Components
See `logical-components.md` for the full list of Kubernetes objects and prerequisite components.
