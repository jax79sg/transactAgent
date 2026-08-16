# Infrastructure Design Plan — Ingestion Worker Service Unit: Local Embedding-Based Semantic Similarity (Epic 9)

## Genuinely open item
None. Mirrors this unit's original Infrastructure Design conventions (internal-only service, no host port
unless something external needs it, healthcheck via the service's own signal).

## Decisions
1. **New `docker-compose` service `vector-db`**: `qdrant/qdrant` image, bind-mounted volume for persistence
   (`./data/qdrant:/qdrant/storage`, same pattern as `database`'s `./data/postgres`), **no host port mapping**
   — only `ingestion-worker` talks to it, same reasoning as `ingestion-worker` itself having no port. Healthcheck
   via Qdrant's own `/healthz` endpoint (wget, same tool already proven to work in this stack's `frontend`
   healthcheck).
2. **`ingestion-worker` gains**: `QDRANT_HOST`/`QDRANT_PORT` (internal service DNS name + Qdrant's default port
   6333), `EMBEDDING_BASE_URL` (no default — host-native oMLX endpoint is entirely user-managed per NFR-5,
   unlike `OPENROUTER_BASE_URL` which has a real working default), `EMBEDDING_MODEL`
   (`embeddinggemma-300m` default), `EMBEDDING_SIMILARITY_THRESHOLD`/`EMBEDDING_TOP_K`/
   `EMBEDDING_BATCH_SIZE`/`EMBEDDING_DIMENSIONS` (defaults per NFR Requirements).
3. **`depends_on: vector-db: condition: service_healthy`** added to `ingestion-worker` — but per NFR Design's
   non-blocking-startup pattern, this only gates container *start order* (compose-level), not the worker's own
   startup logic, which still tolerates Qdrant being unreachable at the application level (FR-10).
4. **oMLX itself gets no `docker-compose` entry** — confirmed out of scope again here (Documented Assumption
   #2, requirements.md): it's a host-native, user-managed prerequisite, same as the categorization-LLM oMLX
   instance already running outside this stack.

## Mandatory Artifacts
- [x] `infrastructure-design.md` — updated in place
- [x] `docker-compose.yml` — updated (new `vector-db` service, `ingestion-worker` env additions)
- [x] `.env.example` — updated (new variables)
