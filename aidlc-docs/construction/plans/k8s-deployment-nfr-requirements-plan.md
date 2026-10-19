# NFR Requirements Plan — Kubernetes Deployment Support

## Assessment
Most tech-stack decisions were already pinned down during Requirements Analysis (Helm, ESO, Vault in persistent mode, default StorageClass, OrbStack Ingress/TLS). Two genuine product/ops-level questions remain — everything else below is resolved as an engineering-judgment default and documented in `tech-stack-decisions.md`, not asked as a question, since there's no real product-level ambiguity in choosing e.g. a Vault auth method.

## Plan Steps
- [ ] Ask the 2 remaining genuine questions (HPA thresholds, Ingress controller assumption)
- [ ] Decide and document the rest as tech-stack decisions: ESO↔Vault auth method, Vault init/unseal key-share scheme, probe reuse from existing healthchecks, resource request/limit sizing per service, Helm/Kubernetes API versions targeted
- [ ] Generate `nfr-requirements.md` and `tech-stack-decisions.md` under `aidlc-docs/construction/k8s-deployment/nfr-requirements/`

## Questions

### Question 1: HPA scaling thresholds
For `api-service` and `frontend`'s `HorizontalPodAutoscaler` (FR-K8S-3), what min/max replica bounds and scaling trigger do you want? This app is single-user, so this is really about resilience/headroom rather than handling real traffic spikes.

A) Conservative — min 1, max 3 replicas, scale on 80% average CPU utilization (Recommended — enough to demonstrate real HPA behavior and add restart/rolling-update resilience, without over-provisioning for a single-user app)

B) min 2 (always at least 2 for availability), max 5, scale on 70% average CPU utilization

C) Other (please describe after [Answer]: tag below)

[Answer]: A

### Question 2: Ingress controller
A Kubernetes `Ingress` resource (FR-K8S-8) needs an Ingress controller already running in the cluster to actually do anything — the `Ingress` object alone doesn't provision one. Do you already have one on your OrbStack cluster?

A) Yes, I already have an Ingress controller running (e.g. ingress-nginx) — just target the standard `ingressClassName: nginx`

B) No — include setup instructions/values for installing `ingress-nginx` (the most common choice, works generically beyond OrbStack too) as part of the prerequisite material

C) Not sure / Other (please describe after [Answer]: tag below)

[Answer]: C. You can check, if it doesn't, please perform (B).
