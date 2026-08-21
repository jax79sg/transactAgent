# Kubernetes Deployment Support — Clarification Questions

Your answers resolved most of the design, but a few of them open real follow-on decisions that shouldn't be guessed at:

## Clarification 1: Vault deployment mode
You asked for a HashiCorp Vault installed on the local OrbStack cluster (Q4) for the External Secrets Operator to read from. Vault has two very different setup profiles:

- **Dev mode**: single replica, in-memory storage, auto-unsealed on start, no HA — the standard choice for a local/dev cluster like this one. Simple to install, but data doesn't survive a pod restart (you'd re-populate secrets after any Vault restart).
- **"Real" mode**: persistent storage (e.g. Raft), manual unseal process, potentially multiple replicas — meaningfully more setup and operational overhead, normally reserved for production/shared clusters.

Given this is a local single-user OrbStack cluster, which do you want?

A) Dev mode — simplest, matches the scale of everything else here (Recommended)

B) "Real" mode with persistent storage (accept the extra setup/unseal complexity)

C) Other (please describe after [Answer]: tag below)

[Answer]: B 

## Clarification 2: How do real secret values get into Vault?
You said Vault/ESO won't be part of the Helm chart itself, which makes sense — but something still needs to actually write the real secret values (JWT secret, Gemini/OpenRouter API keys, Google OAuth client secret, DB password) into Vault before the app's `ExternalSecret` objects can sync them. What should that mechanism be?

A) A small helper script (e.g. `scripts/populate-vault-secrets.sh`) that reads the existing `.env` file and runs `vault kv put` for each value — you run it once per environment, not part of the Helm chart

B) Documented manual `vault kv put` commands in a README — no script, you type them yourself

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Clarification 3: Ingress TLS, given no public domain
You confirmed an Ingress (Q6) but noted no public domain is available — which rules out Let's Encrypt/cert-manager's normal HTTP-01/DNS-01 validation (both need a publicly resolvable domain). Since you're on OrbStack specifically: OrbStack has a built-in feature where exposed services automatically get a `*.orb.local` hostname with a locally-trusted HTTPS certificate (no public domain or cert-manager needed) — likely the simplest fit here. Options:

A) Use OrbStack's automatic `*.orb.local` HTTPS (simplest — works out of the box on this specific cluster, but is OrbStack-specific, not portable to another cluster later)

B) Plain HTTP Ingress, no TLS — access via a manually-added `/etc/hosts` entry pointing at the Ingress controller's IP, works on any cluster

C) TLS via cert-manager's self-signed (or private CA) issuer — browser will show an untrusted-certificate warning, but works on any cluster, not just OrbStack

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Clarification 4: Should this actually be installed live on your OrbStack cluster during this session?
This project's convention so far has been to verify every feature against the real running system, not just produce artifacts. This feature is different in kind, though: it means installing cluster-scoped infrastructure (the External Secrets Operator + Vault, in their own namespaces) onto your **real, currently-running local OrbStack cluster**, not just rebuilding a container. Do you want me to actually run the installs and deploy the Helm chart live against OrbStack as part of this work (and show you it running), or produce the chart/manifests/scripts for you to apply yourself?

A) Yes — install ESO + Vault and deploy the app live on my OrbStack cluster, and verify it end-to-end (Recommended, matches this project's existing verification culture)

B) No — just produce the Helm chart, ESO/Vault setup docs/scripts, and instructions; I'll apply them myself

C) Other (please describe after [Answer]: tag below)

[Answer]: B
