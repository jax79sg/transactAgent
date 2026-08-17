# Infrastructure Design — Model Training Unit

## The Real Decision: Postgres Host Access
`transactagent-db` (the `database` service) currently has **no `ports:` mapping** in `docker-compose.yml` — confirmed via `docker compose ps` during Workflow Planning (only `api-service` on 7878 and `frontend` on 8787 are published; `database`/`vector-db` are internal-only). `model-training/`'s scripts run directly on the host (NFR Requirements' platform constraint — mlx-tune needs Metal, which no container on this Mac can reach), so they need a real path to Postgres that doesn't exist today.

### Options considered
1. **Publish a host port for `database`** — simplest, matches how `api-service`/`frontend` already work; both scripts (`curate.py` and `train.py`) run the same way, no split execution model.
2. **Run `curate.py` inside a throwaway container** attached to `transactagent-net` (no host port needed at all) — `curate.py` genuinely has no MLX dependency, so this is *technically* possible for that one script. Rejected: it would mean the unit's two scripts run in two different execution environments (one containerized, one host-native) for what Requirements described as a single, simple "operator runs two scripts" workflow (FR-CFT-10) — added operational complexity for a security benefit that doesn't matter much on a single-operator local dev machine.
3. **Bind the published port to `127.0.0.1` only, not `0.0.0.0`** — no LAN/remote access is ever needed (unlike the frontend, which genuinely needed LAN-IP reachability per this session's earlier CORS fix) — Model Training only ever runs on this same machine.

### Decision
Option 1 + 3: add a `ports:` mapping to the `database` service, bound to loopback only:
```yaml
ports:
  - "127.0.0.1:5433:5432"
```
Port `5433` (not `5432`) chosen defensively — a developer machine commonly has its own local Postgres already listening on the default `5432`; picking a different host port avoids a silent bind conflict at `docker compose up` time. `model-training/.env.example` documents `DB_HOST=localhost` / `DB_PORT=5433` accordingly (distinct from the containers' own internal `DB_HOST=database`/`DB_PORT=5432`, which is unaffected — this is purely an additional host-side entry point, nothing about the existing internal Docker-network connection changes).

## No Other New Infrastructure
- No new Docker volume, network, or service.
- No new container image, no `Dockerfile` for this unit (platform constraint).
- ClearML: SaaS, no local infrastructure.
- HuggingFace Hub: public endpoint, no local infrastructure; the downloaded model weights are cached under mlx-tune's/HuggingFace's own default local cache directory (`~/.cache/huggingface`) — not something this project's infrastructure needs to manage or provision.
