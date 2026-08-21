# transactagent Helm Chart

Deploys the Bank Transaction Insights app (`database`, `api-service`, `ingestion-worker`,
`frontend`, `vector-db`) to Kubernetes. Provider-agnostic — no cloud-specific resources
are used, though the default `values.yaml` is tuned for a local OrbStack cluster.

This chart deliberately does **not** include External Secrets Operator, HashiCorp
Vault, or an Ingress controller — those are cluster-shared prerequisites, installed
once per cluster, documented separately in [`../prerequisites/`](../prerequisites/README.md).

`docker-compose.yml` at the repo root is unaffected by this chart and remains the
recommended path for local development.

## Deploy Order

1. **Install the prerequisites** (ingress-nginx, Vault, External Secrets Operator) —
   see [`../prerequisites/README.md`](../prerequisites/README.md). This also covers
   initializing and unsealing Vault, and creating the Kubernetes-auth role ESO uses.

2. **Populate Vault with real secret values**, once per environment:
   ```bash
   VAULT_ADDR=http://<your-vault-address>:8200 VAULT_TOKEN=<a-token-with-write-access> \
     ../scripts/populate-vault-secrets.sh /path/to/your/.env
   ```
   See [`../scripts/populate-vault-secrets.sh`](../scripts/populate-vault-secrets.sh) —
   it writes exactly the 6 keys this chart's `ExternalSecret` expects
   (`values.yaml`'s `externalSecrets.secretKeys`).

3. **Build and push images** wherever `values.yaml`'s `image.registry` will point
   (out of scope for this chart — FR-K8S-13 — use your own build/push process; a plain
   `docker build` from each unit's existing `Dockerfile` works, same as
   `docker-compose build` does today).

4. **Set `values.yaml`'s `image.registry`** (and adjust `ingress.host` once
   ingress-nginx's Service is actually running and you know its real assigned hostname).

5. **Install the chart**:
   ```bash
   helm install transactagent ./deploy/helm/transactagent \
     --namespace transactagent --create-namespace
   ```
   (The chart also creates the namespace itself via `templates/namespace.yaml` — the
   `--create-namespace` flag is only needed if you install before that template runs,
   which normally isn't the case; harmless either way.)

6. **Verify**:
   ```bash
   kubectl -n transactagent get pods
   kubectl -n transactagent get externalsecret transactagent-secrets   # should show SYNCED
   ```
   Then visit `https://<ingress.host>/` in a browser.

## Values Reference

| Key | Default | Notes |
|---|---|---|
| `namespace` | `transactagent` | All app resources live here. |
| `image.registry` | *(placeholder — must be set)* | Where your pre-built images live. |
| `image.tag` | `latest` | |
| `ingress.host` | `transactagent.k8s.orb.local` | Adjust once ingress-nginx assigns a real hostname. |
| `ingress.className` | `nginx` | |
| `apiService.replicas.min` / `.max` | `1` / `3` | HPA bounds. |
| `apiService.hpa.targetCPUUtilizationPercentage` | `80` | |
| `frontend.replicas.min` / `.max` | `1` / `3` | HPA bounds. |
| `database.storage.size` | `5Gi` | PVC size, cluster's default StorageClass. |
| `vectorDb.storage.size` | `2Gi` | PVC size, cluster's default StorageClass. |
| `externalSecrets.secretStoreName` | `vault-backend` | Must match the `SecretStore` created by the prerequisites. |
| `externalSecrets.vaultServer` | `http://vault.vault.svc.cluster.local:8200` | In-cluster Vault address. |
| `env.*` | (see `values.yaml`) | ~44 non-secret tunables, one-to-one with `.env.example` at the repo root. |

There is deliberately **no** `ingestionWorker.replicas` value — its replica count is
hardcoded to `1` in `templates/ingestion-worker-deployment.yaml` and cannot be
overridden via `values.yaml`. Its poll loop has no leader-election or
concurrency-safety design; running a second replica would double-process ingestion
runs. This is a correctness constraint, not a default.

## What's Explicitly Out of Scope

- Monitoring/observability infrastructure (Prometheus, Grafana, log aggregation)
- CI/CD (image build/push)
- Multi-environment/multi-cluster promotion tooling

See `aidlc-docs/construction/k8s-deployment/infrastructure-design/infrastructure-design.md`
for the full rationale.
