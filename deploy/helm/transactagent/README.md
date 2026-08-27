# transactagent Helm Chart

Deploys the Bank Transaction Insights app (`database`, `api-service`, `ingestion-worker`,
`frontend`, `vector-db`) to Kubernetes. Provider-agnostic — no cloud-specific resources
are used, though the default `values.yaml` is tuned for a local OrbStack cluster.

This chart deliberately does **not** include External Secrets Operator, HashiCorp
Vault, or an Ingress controller — those are cluster-shared prerequisites, installed
once per cluster, documented separately in [`../prerequisites/`](../prerequisites/README.md).

`docker-compose.yml` at the repo root is unaffected by this chart and remains the
recommended path for local development.

> **⚠️ Before deploying against a genuinely empty database**: `0001_initial_schema.py`
> and `0007_recurring_payments.py` have a real, pre-existing migration bug (found live
> during this feature's own testing, unrelated to Kubernetes itself) that makes the
> full migration chain fail on a truly fresh database — exactly what a new PVC gives
> you. The fix is on branch `fix/migration-0001-fresh-db-drift` (PR #4) — merge that
> before installing this chart against an empty database, or `api-service`/
> `ingestion-worker` will crash-loop on startup. Not needed if your database already
> has data (e.g. restored from an existing deployment).

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

3. **Build images**: `docker compose build` (or `docker build` per unit) works as-is —
   image build/push is out of scope for this chart (FR-K8S-13). `values.yaml`'s
   `image.registry` defaults to empty, meaning "use whatever's already in the local
   Docker image store" — this just works on OrbStack, since it shares its Docker image
   store directly with its Kubernetes cluster, no push needed. Set `image.registry`
   explicitly (e.g. `ghcr.io/yourname`) only if deploying somewhere that can't see your
   local images.

4. **Adjust `values.yaml`'s `ingress.host`** to `transactagent.<your-lan-ip>.sslip.io`,
   replacing `192.168.50.113` with your own machine's LAN IP (find it with
   `ipconfig getifaddr en0` or similar). This can't be a `*.orb.local` host — see the
   comment on `ingress.host` in `values.yaml` for why (Google's OAuth redirect-URI
   validator rejects it outright, which breaks Google Drive Connect). A static
   IP/DHCP reservation is strongly recommended: the IP is baked into this hostname,
   the TLS cert (next step), and the Google Cloud Console redirect URI — all three
   need to be redone if it changes.

5. **Generate the self-signed TLS cert** the Ingress needs (Google requires
   `https://` redirect URIs, but doesn't require the cert be CA-trusted — see
   `values.yaml`'s `ingress.tls` comment):
   ```bash
   ../scripts/generate-selfsigned-cert.sh transactagent.192.168.50.113.sslip.io 192.168.50.113
   ```
   Browsers will show an untrusted-cert warning on first visit from every device —
   that's expected; click through (or import the generated cert as a trusted CA once
   to remove it).

6. **Register the redirect URI in Google Cloud Console**: under your OAuth 2.0
   Client's "Authorized redirect URIs", add
   `https://transactagent.192.168.50.113.sslip.io/api/drive/callback` (matching
   whatever host you set in step 4). Without this, Google Drive Connect fails with a
   400 error — see issue #5.

7. **Install the chart**:
   ```bash
   helm install transactagent ./deploy/helm/transactagent \
     --namespace transactagent --create-namespace
   ```
   (The chart also creates the namespace itself via `templates/namespace.yaml` — the
   `--create-namespace` flag is only needed if you install before that template runs,
   which normally isn't the case; harmless either way.)

8. **Verify**:
   ```bash
   kubectl -n transactagent get pods
   kubectl -n transactagent get externalsecret transactagent-secrets   # should show SYNCED
   ```
   Then visit `https://<ingress.host>/` in a browser (expect a self-signed-cert
   warning — click through).

9. **Create your login** (this app has no self-registration):
   ```bash
   ../scripts/create-k8s-user.sh
   ```
   Prompts interactively for a username and password, hashes the password *inside*
   the `api-service` pod using the app's own real hashing code (same approach as
   `README.md`'s docker-compose "Create your login" section), and inserts the user.
   Nothing is typed into any chat/AI session, echoed to the terminal, or passed as a
   `kubectl exec` command-line argument (which would otherwise land in the cluster's
   own audit log) — see the script's own header comment for the full explanation.

10. **Seed default categories** — required before running ingestion, not just
    recommended: `Category` rows (including the reserved `UNSURE` row every
    transaction falls back to) are seeded by a standalone script, the same one
    `README.md`'s docker-compose setup runs manually — they are **not** created by
    any Alembic migration, and the Settings UI's "add category" can't create the
    reserved `UNSURE` row either. Skipping this step makes every ingested
    transaction crash the run (`AttributeError: 'NoneType' object has no attribute
    'id'` in `pipeline.py`'s `_persist_transaction`, found live — see issue #5's
    branch history) on a genuinely fresh database like a new PVC gives you:
    ```bash
    kubectl -n transactagent exec deploy/api-service -- python3 -m transactagent_db.seed_categories
    ```

## Multi-Device Access

The default `ingress.host` is a sslip.io "magic IP" domain
(`transactagent.<your-lan-ip>.sslip.io`), which resolves via ordinary public DNS
straight to that IP — no hosts-file entry needed on any device. Any device that can
route to that LAN IP (i.e. on the same network) can reach the app at
`https://transactagent.<your-lan-ip>.sslip.io/` directly, using the same
self-signed cert and the same `https://` scheme every time (each device will show
its own untrusted-cert warning on first visit — expected, click through).

This replaces an earlier approach (hosts-file entry + plain `http://`, used when
`ingress.host` was a `*.orb.local` domain) — no longer needed, since sslip.io
resolves the same real hostname everywhere rather than relying on OrbStack's
host-machine-only DNS/HTTPS magic.

**Note on caching**: this note applied specifically to OrbStack's proxy for
`*.orb.local` domains, which no longer applies now that `ingress.host` is a
sslip.io domain. If you still see stale content after a rebuild/redeploy, a plain
browser hard-refresh should be sufficient.

## Values Reference

| Key | Default | Notes |
|---|---|---|
| `namespace` | `transactagent` | All app resources live here. |
| `image.registry` | `""` (empty) | Empty means "use local images as-is" (works on OrbStack, no push needed). Set to a real registry only if deploying elsewhere. |
| `image.tag` | `latest` | |
| `ingress.host` | `transactagent.192.168.50.113.sslip.io` | Replace the IP with your own LAN IP. Must resolve to a public-suffix domain (Google OAuth requirement) — can't be `*.orb.local`. |
| `ingress.className` | `nginx` | |
| `ingress.tls.enabled` | `true` | Self-signed cert — see `ingress.tls`'s comment in `values.yaml` for why. |
| `ingress.tls.secretName` | `transactagent-tls` | Created by `../scripts/generate-selfsigned-cert.sh`, not by this chart. |
| `apiService.replicas.min` / `.max` | `1` / `3` | HPA bounds. |
| `apiService.hpa.targetCPUUtilizationPercentage` | `80` | |
| `frontend.replicas.min` / `.max` | `1` / `3` | HPA bounds. |
| `database.storage.size` | `5Gi` | PVC size, cluster's default StorageClass. |
| `vectorDb.storage.size` | `2Gi` | PVC size, cluster's default StorageClass. |
| `externalSecrets.secretStoreName` | `vault-backend` | Must match the `ClusterSecretStore` name from the prerequisites. |
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
