# Cluster-Shared Prerequisites

These three components are installed **once per cluster** and are not owned by, or
part of, the `transactagent` Helm chart — other apps on the same cluster can reuse
them. Nothing in this directory is applied automatically by anything in this repo;
run these commands yourself when you're ready to deploy.

Install order matters: ingress-nginx and External Secrets Operator can go in any
order relative to each other, but Vault must be installed and unsealed, with its
Kubernetes auth method configured, before the `transactagent` chart's
`ExternalSecret` can actually sync anything (the chart will still install fine
either way — it'll just show `SecretSyncError` until Vault is ready).

## 1. ingress-nginx

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  -f ingress-nginx-values.yaml
```

Wait for the controller's Service to get an address (OrbStack auto-assigns one to
`LoadBalancer` Services):
```bash
kubectl -n ingress-nginx get svc ingress-nginx-controller
```

## 2. HashiCorp Vault

```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update
helm install vault hashicorp/vault \
  --namespace vault --create-namespace \
  -f vault-values.yaml
```

### Initialize and unseal (manual, one-time — do this yourself, not via any script)

```bash
kubectl -n vault exec -it vault-0 -- vault operator init
```

This prints 5 unseal key shares and an initial root token, **once**. Store all of
this securely (e.g. a password manager) — it is never written to disk by this
project, never committed to git, and cannot be recovered if lost (you'd need to
re-init Vault and re-run the secret-population script).

Unseal (needs 3 of the 5 key shares — repeat this command 3 times with 3 different
keys):
```bash
kubectl -n vault exec -it vault-0 -- vault operator unseal
```

Vault is sealed again after every pod restart — you'll need to repeat the unseal
step then too. This is the accepted tradeoff of persistent/Raft mode over `dev`
mode, per the project's own requirements (`k8s-deployment-requirements.md`,
clarification C1).

### Enable the KV v2 secrets engine and write the app's policy

From your own machine, with `VAULT_ADDR` pointed at Vault (port-forward if needed:
`kubectl -n vault port-forward svc/vault 8200:8200`) and `VAULT_TOKEN` set to the
root token from init:

```bash
vault secrets enable -path=secret kv-v2

cat <<'EOF' | vault policy write transactagent-read -
path "secret/data/transactagent" {
  capabilities = ["read"]
}
EOF
```

### Enable Kubernetes auth and bind it to ESO's ServiceAccount

```bash
vault auth enable kubernetes

vault write auth/kubernetes/config \
  kubernetes_host="https://kubernetes.default.svc"

vault write auth/kubernetes/role/transactagent \
  bound_service_account_names=external-secrets \
  bound_service_account_namespaces=external-secrets \
  policies=transactagent-read \
  ttl=1h
```

This is what `transactagent`'s `ClusterSecretStore` (`deploy/helm/transactagent/templates/externalsecret.yaml`)
references as `auth.kubernetes.role: transactagent` — the chart's `ClusterSecretStore`
and this Vault-side role name must match (both default to `transactagent`).

Note it's a `ClusterSecretStore`, not a namespaced `SecretStore` — found live: a
namespaced `SecretStore`'s admission webhook rejects a `serviceAccountRef` outside
its own namespace, but ESO's ServiceAccount lives in the `external-secrets`
namespace, not `transactagent`. The real isolation still comes from the Vault policy
above (`secret/data/transactagent` only), not from the Kubernetes object's own
namespace scope.

## 3. External Secrets Operator

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets --create-namespace \
  -f external-secrets-values.yaml
```

Verify it's running:
```bash
kubectl -n external-secrets get pods
```

## Next Step

Once all three are installed and Vault is unsealed with its policy/auth role
configured, populate Vault with your real secret values — see
[`../scripts/populate-vault-secrets.sh`](../scripts/populate-vault-secrets.sh) — then
follow [`../transactagent/README.md`](../transactagent/README.md) to install the app
chart itself.
