#!/usr/bin/env bash
# Generates a self-signed TLS cert/key for the Ingress and stores it as a Kubernetes
# Secret, so templates/ingress.yaml's `tls:` block has something to reference.
#
# Why self-signed rather than a real CA-issued cert: values.yaml's default
# ingress.host is a sslip.io "magic IP" domain (e.g. transactagent.192.168.50.113.
# sslip.io), chosen specifically because Google's OAuth redirect-URI validator
# rejects non-public-TLD domains outright (*.orb.local, *.local, etc. -- see
# aidlc-docs/audit.md for the investigation). Google's validator only checks that
# the redirect URI's domain is a real public suffix; it does NOT check that the
# TLS certificate is CA-trusted. So a self-signed cert satisfies Google's OAuth
# requirement (https://, valid public-suffix domain) while needing no public
# port-forwarding or DNS-01 setup (sslip.io's zone isn't yours to add TXT records
# to, so Let's Encrypt's DNS-01 challenge isn't an option here). The one real
# cost: browsers will show a security warning on first visit from every device,
# since nothing trusts this cert's CA. Click through (or import the generated
# cert as a trusted CA on your test devices, once, to remove the warning).
#
# Usage: ./generate-selfsigned-cert.sh <host> <ip> [namespace] [secret-name]
#   host        e.g. transactagent.192.168.50.113.sslip.io (must match values.yaml's ingress.host)
#   ip          e.g. 192.168.50.113 (included as a SAN so IP-based access also validates)
#   namespace   default: transactagent
#   secret-name default: transactagent-tls (must match values.yaml's ingress.tls.secretName)
#
# Safe to re-run (e.g. before renewal -- 825 days is the browser-enforced max
# validity for a leaf cert): recreates the Secret in place via `kubectl apply`.

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <host> <ip> [namespace] [secret-name]" >&2
  exit 1
fi

HOST="$1"
IP="$2"
NAMESPACE="${3:-transactagent}"
SECRET_NAME="${4:-transactagent-tls}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "Error: the 'openssl' CLI is not installed or not on PATH." >&2
  exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "Error: the 'kubectl' CLI is not installed or not on PATH." >&2
  exit 1
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "Generating self-signed cert for $HOST (IP SAN: $IP), valid 825 days..."
openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "$WORKDIR/tls.key" \
  -out "$WORKDIR/tls.crt" \
  -days 825 \
  -subj "/CN=$HOST" \
  -addext "subjectAltName=DNS:$HOST,IP:$IP"

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

kubectl -n "$NAMESPACE" create secret tls "$SECRET_NAME" \
  --cert="$WORKDIR/tls.crt" \
  --key="$WORKDIR/tls.key" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Secret '$SECRET_NAME' ready in namespace '$NAMESPACE'."
echo "Remember: browsers will warn about this cert being untrusted on first visit -- that's expected."
