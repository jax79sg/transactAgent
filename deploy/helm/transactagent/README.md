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

7. **Create your login** (this app has no self-registration):
   ```bash
   ../scripts/create-k8s-user.sh
   ```
   Prompts interactively for a username and password, hashes the password *inside*
   the `api-service` pod using the app's own real hashing code (same approach as
   `README.md`'s docker-compose "Create your login" section), and inserts the user.
   Nothing is typed into any chat/AI session, echoed to the terminal, or passed as a
   `kubectl exec` command-line argument (which would otherwise land in the cluster's
   own audit log) — see the script's own header comment for the full explanation.

## Multi-Device Access

The default `ingress.host` (`transactagent.k8s.orb.local`) resolves automatically,
with trusted HTTPS, **only on the machine OrbStack itself runs on** — that DNS/TLS
magic is host-local, not something another device on your network can use. To reach
the app from another device:

1. Add a hosts-file entry on that device pointing the same hostname at this Mac's
   LAN IP (find it with `ipconfig getifaddr en0` or similar), e.g.:
   ```
   192.168.1.50 transactagent.k8s.orb.local
   ```
2. Access it over **plain `http://`**, not `https://` — the other device has no way
   to trust OrbStack's local-only certificate. This works correctly without any
   further configuration: the frontend derives its API calls from whatever
   scheme/host actually loaded the page (see `frontend/src/config.ts`'s
   `apiBasePath` handling), rather than assuming a fixed one.

**Note on caching**: OrbStack's own proxy for `*.orb.local` domains caches responses
by exact URL. After a rebuild/redeploy, a page you'd already loaded may keep showing
old content until you hard-refresh or add a cache-busting query string (e.g.
`?cb=1`) — the deployment itself has already updated; this is purely a client-facing
caching quirk of OrbStack's proxy layer.

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
