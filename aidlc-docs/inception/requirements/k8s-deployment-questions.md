# Kubernetes Deployment Support — Clarifying Questions

Source: GitHub issue #2 ("Support for deployment into K8S") — "Make this a scalable deployment on K8S please."

Context found while reviewing the current setup: this app runs today via `docker-compose.yml` as 5 services (`database` Postgres, `api-service`, `ingestion-worker`, `frontend`, `vector-db` Qdrant), all on one Docker host, with local bind-mount volumes for Postgres/Qdrant data and a shared `settings-override` volume. It's an explicitly **single-user** app (`personas.md`: "single-user, no multi-user account management"). A separate `model-training/` unit runs directly on the host (not containerized — needs macOS/Metal, has no `docker-compose` entry at all) and is out of scope for this containerized deployment regardless of answers below. The `ingestion-worker` is a singleton poll-loop with no leader-election or concurrency-safety design — running more than one replica of it at once is a correctness risk, not just a resource question.

Please answer each question by filling in the letter choice after the `[Answer]:` tag. If none of the options match, choose the last option (Other) and describe your preference. Let me know when you're done.

## Question 1
What does "scalable" mean for this specific app? (Important: since it's single-user, more replicas doesn't mean more capacity the way it would for a multi-tenant app.)

A) Production-grade orchestration and resilience (auto-restart, rolling updates, resource limits, proper health checks) — not literal horizontal autoscaling, since a single-user app has no real multi-replica workload

B) Genuine horizontal autoscaling (HPA) on the stateless, safely-replicable services (`api-service`, `frontend`) for handling traffic spikes, while `ingestion-worker` and `database` stay single-replica (they're stateful/singleton by design)

C) Both A and B

D) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 2
Where will this run?

A) Local/dev cluster (Docker Desktop Kubernetes, minikube, or kind) — no cloud provider involved

B) A managed cloud Kubernetes service (EKS, GKE, AKS, or similar)

C) Generic/on-prem cluster, provider-agnostic manifests (no cloud-specific resources like LoadBalancer/cloud storage classes)

D) Other (please describe after [Answer]: tag below)

[Answer]: D. I already have orbstack k8s running on the machine. Make sure the manifest is provider-agnostic.

## Question 3
What deliverable format do you want?

A) A Helm chart (parameterized, versioned, `helm install`-able)

B) Kustomize base + overlays (plain YAML, patch-based environment variants)

C) Plain Kubernetes YAML manifests (simplest, least tooling, least flexible)

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 4
How should secrets (JWT secret, Gemini/OpenRouter API keys, Google OAuth client secret, DB password — currently plain env vars from a `.env` file) be supplied to the cluster?

A) Native Kubernetes `Secret` objects, created manually by whoever deploys (documented, not automated) — simplest, matches this project's existing "you manage your own `.env`" pattern

B) Native Kubernetes `Secret` objects, generated from the existing `.env` file by a provided script/Helm value, so the migration is close to drop-in

C) An external secrets manager (e.g. Sealed Secrets, External Secrets Operator) — adds real setup complexity, only worth it if you already use one

D) Other (please describe after [Answer]: tag below)

[Answer]: D. Install the https://external-secrets.io/latest/ external secrets operator on the local K8S. Also setup a HashiCorp Vault on the local K8S on a different namespace for the operator to call the API. Note HashiCorp and operator will not be part of the helm chart, they should be available to all applications.

## Question 5
Postgres and Qdrant currently persist to local bind-mounted directories (`./data/postgres`, etc.). In Kubernetes this needs to become a `PersistentVolumeClaim`. What's the target?

A) Whatever `StorageClass` is already configured as default on the target cluster (portable, no assumptions) — you (or whoever deploys) pick the size

B) A specific storage setup you already have in mind (please describe under Other — e.g. a particular cloud disk type, NFS, local-path-provisioner)

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 6
How should the app be reached from outside the cluster?

A) A Kubernetes `Ingress` with a real hostname (TLS via cert-manager/Let's Encrypt if a domain is available)

B) Simple `NodePort` / `kubectl port-forward` — no ingress controller assumed, matches today's "just hit `localhost:8787`" simplicity

C) A cloud `LoadBalancer` Service (only sensible if Q2 = managed cloud)

D) Other (please describe after [Answer]: tag below)

[Answer]: A. No domain will be available.

## Question 7
Where do the container images come from? (Today, `docker compose build` builds them locally from each unit's `Dockerfile`.)

A) Manifests/chart assume pre-built images already exist in some registry — building and pushing them is a separate, manual step you'll handle yourself (not part of this feature)

B) Include a CI pipeline (e.g. GitHub Actions) that builds and pushes images to a registry (please name the registry under Other if you have one, e.g. GHCR/Docker Hub/ECR)

C) Assume purely local images (`kind load docker-image` / Docker Desktop's shared image cache) — fine for local/dev clusters (Q2 = A) only

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 8
Should `docker-compose.yml` (local dev workflow) be kept as-is alongside the new Kubernetes deployment, or is Kubernetes meant to fully replace it?

A) Keep `docker-compose.yml` for local dev, add Kubernetes purely as a new deployment option (most projects keep both)

B) Kubernetes fully replaces Docker Compose going forward

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 9
The `EMBEDDING_BASE_URL` (oMLX server, used for semantic similarity) currently points to a host-machine service outside Docker Compose entirely (macOS/Metal-only, can't be containerized — same constraint as `model-training/`). In a Kubernetes deployment, how should the cluster reach it?

A) Treat it exactly like today — an external URL the cluster calls out to (works as long as the cluster has network egress to wherever that host is); no special K8s networking needed

B) It won't be reachable from the target cluster (e.g. a cloud cluster that can't reach your home Mac) — embedding-based matching should be expected to gracefully degrade (per its existing no-retry/soft-fail design) rather than something this feature needs to solve

C) Other (please describe after [Answer]: tag below)

[Answer]: A
