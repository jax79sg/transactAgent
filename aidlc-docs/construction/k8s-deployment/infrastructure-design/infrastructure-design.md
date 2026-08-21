# Infrastructure Design — Kubernetes Deployment Support

## Out of Scope (explicit)
- **Monitoring/observability infrastructure** (Prometheus, Grafana, log aggregation) — never requested by the issue or any FR/NFR. Baseline health visibility comes from the existing probe design (`nfr-design-patterns.md`); adding a full monitoring stack here would be unrequested scope creep for a single-user app.
- **CI/CD pipeline** — FR-K8S-13 explicitly puts image build/push out of scope.
- **Multi-environment/multi-cluster promotion pipeline** — one `values.yaml` (plus room for environment-specific override files) is sufficient; nothing in the requirements asked for a staging/prod split.

## Chart File Layout

```
deploy/
├── helm/
│   ├── transactagent/                      # this app's chart (FR-K8S-1)
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   ├── README.md                       # end-to-end deploy instructions
│   │   └── templates/
│   │       ├── namespace.yaml
│   │       ├── configmap.yaml               # non-secret env vars
│   │       ├── externalsecret.yaml          # ExternalSecret + SecretStore
│   │       ├── database-statefulset.yaml
│   │       ├── database-service.yaml
│   │       ├── database-pvc.yaml
│   │       ├── database-networkpolicy.yaml
│   │       ├── vector-db-statefulset.yaml
│   │       ├── vector-db-service.yaml
│   │       ├── vector-db-pvc.yaml
│   │       ├── vector-db-networkpolicy.yaml
│   │       ├── api-service-deployment.yaml
│   │       ├── api-service-service.yaml
│   │       ├── api-service-hpa.yaml
│   │       ├── frontend-deployment.yaml
│   │       ├── frontend-service.yaml
│   │       ├── frontend-hpa.yaml
│   │       ├── ingestion-worker-deployment.yaml
│   │       └── ingress.yaml
│   └── prerequisites/                       # cluster-shared, NOT part of the app chart (FR-K8S-5/6)
│       ├── README.md                        # install order + commands
│       ├── ingress-nginx-values.yaml
│       ├── vault-values.yaml
│       └── external-secrets-values.yaml
└── scripts/
    └── populate-vault-secrets.sh            # FR-K8S-7
```

## `values.yaml` Schema Outline
```yaml
namespace: transactagent

image:
  registry: ""            # e.g. ghcr.io/jax79sg -- left blank, user fills in per FR-K8S-13
  tag: "latest"

ingress:
  host: transactagent.k8s.orb.local   # adjust once ingress-nginx's Service is actually running
  className: nginx

apiService:
  replicas: { min: 1, max: 3 }
  hpa: { targetCPUUtilizationPercentage: 80 }
  resources: { requests: { cpu: 100m, memory: 128Mi }, limits: { cpu: 500m, memory: 512Mi } }

frontend:
  replicas: { min: 1, max: 3 }
  hpa: { targetCPUUtilizationPercentage: 80 }
  resources: { requests: { cpu: 50m, memory: 64Mi }, limits: { cpu: 200m, memory: 128Mi } }

ingestionWorker:
  resources: { requests: { cpu: 100m, memory: 128Mi }, limits: { cpu: 500m, memory: 512Mi } }
  # no replicas field -- hardcoded to 1 in the template (NFR-K8S-5)

database:
  storage: { size: 5Gi }               # storageClassName intentionally omitted -- cluster default (Q5=A)
  resources: { requests: { cpu: 250m, memory: 256Mi }, limits: { cpu: 1, memory: 1Gi } }

vectorDb:
  storage: { size: 2Gi }
  resources: { requests: { cpu: 200m, memory: 256Mi }, limits: { cpu: 1, memory: 1Gi } }

externalSecrets:
  secretStoreName: vault-backend         # SecretStore assumed already created by the prerequisite install
  vaultPath: secret/transactagent        # matches populate-vault-secrets.sh's target path

env:
  # all ~40 non-secret tunables from .env.example, as plain key/value pairs consumed by configmap.yaml
  ...
```

## Prerequisite Install References (documentation only — not executed this session, per NFR-K8S-3)
| Component | Upstream chart | Namespace | Notes |
|---|---|---|---|
| ingress-nginx | `ingress-nginx/ingress-nginx` | `ingress-nginx` | Confirmed absent on the target cluster via live read-only check. |
| HashiCorp Vault | `hashicorp/vault` | `vault` | `server.dataStorage.enabled=true`, `server.ha.enabled=false` (single-node Raft, per C1=B). Requires a manual `vault operator init` + unseal after install — not automatable without exposing unseal keys somewhere unsafe. |
| External Secrets Operator | `external-secrets/external-secrets` | `external-secrets` | After install: a `ClusterSecretStore` (or namespaced `SecretStore`) object pointing at Vault via the Kubernetes auth method — created as part of the prerequisites material, not the app chart. |

## Code Generation Hand-off
This document plus `logical-components.md`/`nfr-design-patterns.md` are sufficient to generate every file listed above. No further design questions are open.
