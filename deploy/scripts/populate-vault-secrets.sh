#!/usr/bin/env bash
# Reads the real secret values from a .env file and writes them into Vault, at the
# single path the transactagent chart's ExternalSecret reads from
# (secret/transactagent -- see deploy/helm/transactagent/values.yaml's
# externalSecrets.vaultPath). Run this once per environment, manually, after Vault is
# installed/unsealed and before `helm install`ing the app chart (see
# deploy/helm/prerequisites/README.md and deploy/helm/transactagent/README.md).
#
# This script never stores or logs a secret value anywhere except by handing it
# directly to `vault kv put` -- it does not write a temp file, does not echo values,
# and is not itself part of the Helm chart (FR-K8S-7).
#
# Usage: VAULT_ADDR=... VAULT_TOKEN=... ./populate-vault-secrets.sh [path/to/.env]
#   (defaults to ../../.env relative to this script, i.e. the repo root's .env)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${1:-"$SCRIPT_DIR/../../.env"}"
VAULT_PATH="secret/transactagent"

# Exactly the keys deploy/helm/transactagent/values.yaml's externalSecrets.secretKeys
# expects -- keep these two lists in sync if either changes.
SECRET_KEYS=(
  DB_PASSWORD
  JWT_SECRET
  GOOGLE_OAUTH_CLIENT_SECRET
  GEMINI_API_KEY
  OPENROUTER_API_KEY
  EMBEDDING_API_KEY
)

if [ ! -f "$ENV_FILE" ]; then
  echo "Error: env file not found at $ENV_FILE" >&2
  echo "Usage: VAULT_ADDR=... VAULT_TOKEN=... $0 [path/to/.env]" >&2
  exit 1
fi

if ! command -v vault >/dev/null 2>&1; then
  echo "Error: the 'vault' CLI is not installed or not on PATH." >&2
  exit 1
fi

if [ -z "${VAULT_ADDR:-}" ] || [ -z "${VAULT_TOKEN:-}" ]; then
  echo "Error: VAULT_ADDR and VAULT_TOKEN must both be set in the environment." >&2
  echo "(e.g. VAULT_ADDR=http://localhost:8200 after 'kubectl -n vault port-forward svc/vault 8200:8200')" >&2
  exit 1
fi

# Reads a KEY=value line's value out of the .env file without sourcing the whole file
# (sourcing an arbitrary .env would execute anything else in it) -- only ever looks up
# the exact keys in SECRET_KEYS, ignores comments and everything else in the file.
read_env_value() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d'=' -f2-
}

KV_ARGS=()
MISSING=()
for key in "${SECRET_KEYS[@]}"; do
  value="$(read_env_value "$key")"
  if [ -z "$value" ] || [ "$value" = "changeme" ]; then
    MISSING+=("$key")
    continue
  fi
  KV_ARGS+=("${key}=${value}")
done

if [ ${#MISSING[@]} -gt 0 ]; then
  echo "Warning: the following keys are missing or still set to 'changeme' in $ENV_FILE and will be skipped:" >&2
  printf '  - %s\n' "${MISSING[@]}" >&2
  echo "(EMBEDDING_API_KEY being empty is expected/fine if you don't use a keyed embedding server.)" >&2
fi

if [ ${#KV_ARGS[@]} -eq 0 ]; then
  echo "Error: no secret values found to write -- check $ENV_FILE." >&2
  exit 1
fi

vault kv put "$VAULT_PATH" "${KV_ARGS[@]}"

echo "Wrote ${#KV_ARGS[@]} secret(s) to Vault at $VAULT_PATH."
