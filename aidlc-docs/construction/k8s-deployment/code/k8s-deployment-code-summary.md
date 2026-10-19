# Code Summary — Kubernetes Deployment Support (Epic/Issue #2)

Cross-cutting feature — not owned by one existing unit. No application code in any of
the 5 existing services changed; `docker-compose.yml` untouched.

## Files Created

**Helm chart** (`deploy/helm/transactagent/`):
- `Chart.yaml`, `values.yaml`, `README.md`
- `templates/namespace.yaml`, `templates/configmap.yaml`, `templates/externalsecret.yaml`
- `templates/database-statefulset.yaml`, `templates/database-service.yaml`, `templates/database-networkpolicy.yaml`
- `templates/vector-db-statefulset.yaml`, `templates/vector-db-service.yaml`, `templates/vector-db-networkpolicy.yaml`
- `templates/api-service-deployment.yaml`, `templates/api-service-service.yaml`, `templates/api-service-hpa.yaml`
- `templates/frontend-deployment.yaml`, `templates/frontend-service.yaml`, `templates/frontend-hpa.yaml`
- `templates/ingestion-worker-deployment.yaml`
- `templates/ingress.yaml`

**Prerequisites** (`deploy/helm/prerequisites/`): `README.md`, `ingress-nginx-values.yaml`, `vault-values.yaml`, `external-secrets-values.yaml`

**Script**: `deploy/scripts/populate-vault-secrets.sh`

## Deviations From the Infrastructure Design Sketch (both deliberate improvements)
- **PVCs**: `infrastructure-design.md` listed separate `database-pvc.yaml`/`vector-db-pvc.yaml` template files. Implemented instead via each `StatefulSet`'s `volumeClaimTemplates` — the idiomatic Kubernetes pattern for a singleton stateful workload's storage, and simpler/more correct than manually wiring a standalone `PersistentVolumeClaim` + volume-by-name reference.
- **Ingress path rewriting**: not explicitly called out in the design docs, but discovered as a real correctness issue during Code Generation — `api-service`'s actual routes are `/health`, `/transactions`, etc., not `/api/health`, so routing `/api` straight through without stripping the prefix would have 404'd every API call. Fixed via the standard `ingress-nginx` `rewrite-target` + regex-capture pattern (`templates/ingress.yaml`).

## Verification (Build and Test, scope-limited per NFR-K8S-3 — no live cluster changes)
- `helm lint /charts/transactagent` (via `alpine/helm:latest`, no local Helm install): clean — 0 errors, 1 harmless "icon is recommended" info notice.
- `helm template`: renders 18 valid YAML documents — 1 Namespace, 3 Deployments, 2 StatefulSets, 2 HPAs, 4 Services, 2 NetworkPolicies, 1 ConfigMap, 1 Ingress, 1 SecretStore, 1 ExternalSecret. Parsed successfully with Python's `yaml.safe_load_all` (structural sanity) and every document confirmed to carry both `kind` and `apiVersion`.
- **`kubectl apply --dry-run=client`** against the user's real OrbStack cluster (client-side only — validates against the cluster's real API schema, mutates nothing): all 16 standard-Kubernetes resources validated clean (`... created (dry run)`). The 2 remaining resources (`ExternalSecret`, `SecretStore`) correctly fail with "no matches for kind ... ensure CRDs are installed first" — expected and correct, since External Secrets Operator's CRDs genuinely aren't installed on this cluster yet (confirmed absent during NFR Requirements); not a chart defect.
- **Replica-safety constraint (NFR-K8S-5) verified structurally, not just asserted**: rendered with `--set ingestionWorker.replicas=5` (a nonsense override — no such values field exists) and confirmed the `ingestion-worker` Deployment still renders `replicas: 1` unchanged. Confirmed `api-service`/`frontend` Deployments render with zero `replicas:` occurrences (HPA-owned, as designed).
- **Values propagation verified**: rendered with `--set image.registry=... --set image.tag=... --set ingress.host=...` and confirmed the image reference, the Ingress host, and `frontend`'s derived `API_BASE_URL` all updated consistently together.

## Explicitly Not Done This Session (per NFR-K8S-3 / user's C4=B)
- No `helm install` against the real OrbStack cluster.
- No installation of ingress-nginx, Vault, or External Secrets Operator.
- No Vault init/unseal, no secret values written anywhere.
