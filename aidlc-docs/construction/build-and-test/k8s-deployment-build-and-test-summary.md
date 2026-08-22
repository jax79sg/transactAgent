# Build and Test Summary — Kubernetes Deployment Support (GitHub Issue #2)

Cross-cutting feature — no existing unit's application code changed; `docker-compose.yml` untouched and unaffected.

## Build Status
- **Build Tool**: Helm 4 (`v4.2.4`, via the official `alpine/helm:latest` image — no local Helm install)
- **Build Status**: Success
- **Build Artifacts**: `deploy/helm/transactagent/` (chart), `deploy/helm/prerequisites/` (values files, no chart of their own — they configure the official upstream ingress-nginx/Vault/external-secrets charts), `deploy/scripts/populate-vault-secrets.sh`

## Test Execution Summary

### Static Validation
- `helm lint --strict`: clean — 0 errors, 1 harmless info notice ("icon is recommended")
- `helm template`: renders 18 valid YAML documents (1 Namespace, 3 Deployments, 2 StatefulSets, 2 HorizontalPodAutoscalers, 4 Services, 2 NetworkPolicies, 1 ConfigMap, 1 Ingress, 1 SecretStore, 1 ExternalSecret) — parsed successfully with `yaml.safe_load_all`, every document confirmed to carry both `kind` and `apiVersion`
- `shellcheck` on `populate-vault-secrets.sh` (via `koalaman/shellcheck:stable`): clean, exit code 0
- All 3 prerequisite values files (`ingress-nginx-values.yaml`, `vault-values.yaml`, `external-secrets-values.yaml`) parsed as valid YAML

### Live Schema Validation (real cluster, zero mutation)
`kubectl apply --dry-run=client -f -` against the user's real running OrbStack cluster — client-side only, validates structure/schema against the cluster's actual API surface, creates or modifies nothing:
- **16 of 18 rendered resources validated clean** (`... created (dry run)`): Namespace, both NetworkPolicies, ConfigMap, all 4 Services, all 3 Deployments, both HPAs, both StatefulSets, the Ingress
- **2 resources (`ExternalSecret`, `SecretStore`) correctly failed** with "no matches for kind ... ensure CRDs are installed first" — this is expected and correct, not a defect: External Secrets Operator's CRDs genuinely aren't installed on this cluster (confirmed absent during NFR Requirements via a separate read-only check). Once ESO is installed per `deploy/helm/prerequisites/README.md`, these same manifests will validate the same way the other 16 did.

### Behavioral/Structural Verification
- **Replica-safety constraint (NFR-K8S-5)**: re-verified by attempting `helm template --set ingestionWorker.replicas=5` — since no such `values.yaml` field exists (deliberately), the rendered `ingestion-worker` Deployment still shows `replicas: 1`, unchanged. Also confirmed `api-service`/`frontend` Deployments render with zero `replicas:` occurrences (correctly left to the HPA).
- **Values propagation**: rendered with `--set image.registry=... --set image.tag=... --set ingress.host=...` and confirmed the image reference, Ingress host, and frontend's derived `API_BASE_URL` all update together consistently, with no stale/mismatched values anywhere in the output.
- **Real bug found and fixed via this same rendering process** (not left for a future incident): the Ingress's `/api` path, without prefix-stripping, would have forwarded requests to `api-service` still carrying the `/api` prefix — but `api-service`'s actual FastAPI routes are `/health`, `/transactions`, etc., not `/api/health`, so every browser-originated API call would have 404'd. Fixed via `ingress-nginx`'s standard `rewrite-target` annotation + regex-capture path pattern; re-verified in the rendered output.

### Integration / E2E / Performance / Contract / Security Tests
- **N/A** — no live cluster changes were made this session (per NFR-K8S-3 / the user's explicit choice, requirements clarification C4=B), so there's no running instance of any new resource to run these tests against. What live validation *was* possible without mutating the cluster (schema/dry-run checks above) was performed and is real, not skipped or assumed.

## What Real End-to-End Verification Would Still Require (for whoever applies this)
Documented here so it isn't silently implied to already be done:
1. Actually installing ingress-nginx, Vault, and External Secrets Operator (`deploy/helm/prerequisites/README.md`)
2. Initializing/unsealing Vault and configuring its Kubernetes auth role
3. Building and pushing the 3 application images somewhere `values.yaml`'s `image.registry` can reach
4. Running `populate-vault-secrets.sh` against a real `.env`
5. `helm install`, then confirming `kubectl -n transactagent get externalsecret transactagent-secrets` shows `SYNCED` and the app is actually reachable at the Ingress host

## Overall Status
- **Build**: Success
- **All Tests (within this session's scope)**: Pass
- **Ready for Operations**: The chart/scripts/docs are ready for the user to apply themselves, per their explicit choice not to have this installed live this session. The 5-step checklist above is the actual remaining work, owned by the user, not part of this feature's Build and Test.
