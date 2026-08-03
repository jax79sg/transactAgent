# Infrastructure Design — Unit 1: Database

## Docker Compose Service: `database`

```yaml
services:
  database:
    image: postgres:16-alpine
    container_name: transactagent-db
    environment:
      POSTGRES_DB: ${DB_NAME:-transactagent}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME:-transactagent}"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s
    restart: unless-stopped
    networks:
      - transactagent-net
```

**Notes**:
- **No `ports:` mapping** (Question 2 = B) — only reachable by other containers on the `transactagent-net` compose network, not from the host machine. To inspect the DB directly during development, use `docker exec -it transactagent-db psql -U $DB_USER -d transactagent` or temporarily add a port mapping.
- **Bind mount** (Question 1 = B) to `./data/postgres` at the workspace root — visible, host-inspectable, easy to back up by copying the folder. This directory should be added to `.gitignore` (it's runtime data, not source).
- **Healthcheck** (Question 3 = A) uses `pg_isready`; Units 2 and 3's compose service definitions (finalized in their own Infrastructure Design stages) will declare `depends_on: { database: { condition: service_healthy } }` so they never even attempt to connect before Postgres is accepting connections. This is in addition to, not a replacement for, the advisory-lock-guarded migration each of those units runs at their own startup (NFR Design).
- **Credentials** (`DB_USER`, `DB_PASSWORD`) are supplied via `.env` (NFR-4.1) — never hardcoded in `docker-compose.yml` or committed to source control. `DB_NAME` defaults to `transactagent` if unset.
- **`restart: unless-stopped`** — standard resilience for a long-running local service; if the container crashes, Docker restarts it automatically unless you explicitly stopped it.

## Required Environment Variables (added to `.env.example`)

```
DB_NAME=transactagent
DB_USER=transactagent_app
DB_PASSWORD=changeme
```
