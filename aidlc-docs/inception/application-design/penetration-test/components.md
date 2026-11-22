# Penetration Test — Components

Scope: the new `pentest/` project. No existing product component changes. Signatures are in
`component-methods.md`; rules (exact thresholds, schemas, test lists) are decided later in Functional Design.
Decisions D1 to D15 are from `inception/plans/penetration-test-application-design-plan.md`; the owner's answers to
its four questions are folded in (Q1 A, Q2 B, Q3 C, Q4 A).

## Layout

```
pentest/
  pyproject.toml, uv.lock          own dependency file (PT-NFR-6)
  src/pentest/                     the library: all components below
  tests/                           tests OF the harness (guard, linter, seed, stubs, normaliser, validator, ...)
  suite/                           Track B: the penetration tests AGAINST the stack
  stack/                           compose project, runner image, stub image, seed image
  audit/                           Track A: PROCEDURE.md, ledger, work-package template, schema
  live_check.py                    the separate live exposure check
aidlc-docs/construction/pentest/   findings.json, ledger.json, REPORT.md (generated)
.github/workflows/pentest.yml      hand-started workflow
```

## C1. Stack Manager (`stack.py`)

**Purpose:** build, start, health-check and tear down the throwaway stack as one compose project of its own.

**Responsibilities**
- Render the compose configuration and hand it to the Compose Linter before anything starts.
- Build the product images from the current checkout under project-prefixed tags; record image digests and the
  commit, and whether the application source directories were clean (so "unmodified code" is a recorded fact).
- Start the services with hard CPU, memory and process limits on every container (Q3).
- Wait for health; confirm the schema reached the migration head from an empty database (the API applies the real
  migrations at start).
- Set the synthetic-data marker on the database (D4).
- Export the built images as tarballs for the offline Trivy scan (D9).
- Tear down, volumes included, in all outcomes; prove nothing is left behind.

**Interfaces:** used by the Run Orchestrator; reads the stack definition under `pentest/stack/`; talks to Docker
through the `docker` command line. Publishes **no ports** (Q4 = A).

## C2. Compose Linter (`linter.py`)

**Purpose:** refuse to start a stack that could touch the live one. Host side, static, before `up`.

**Responsibilities**
- Check the rendered configuration against the safety rules in D3: project name, no `container_name`, no bind
  mount, no `./data`, no published port, no external network or volume, no `network_mode: host`, no Docker
  socket mount, every network internal, every image pinned, limits present on every service.
- Learn the live stack's identity (container names, published ports, database name) by reading the repository's own
  `docker-compose.yml`, never the live `.env` or the running stack.
- **Parity check:** compare the throwaway service definitions with the real compose file (same Dockerfiles,
  same environment variable names, same health checks) and list every difference, so the throwaway stack cannot
  silently drift away from what ships. Allowed differences are an explicit, short list.

**Interfaces:** pure functions over a rendered configuration; no Docker access of its own.

## C3. Request Guard (`guard.py`)

**Purpose:** the second, independent control. Runs inside the runner on every request and refuses anything but
the throwaway stack.

**Responsibilities**
- Allow only the throwaway project's own service names on its own ports (allowlist).
- Independently refuse the live hostnames, ports and database name, and any database that lacks the
  synthetic-data marker (denylist and marker check).
- Provide a self-test that exercises every live port and name and shows each is refused; its tests run before any
  request goes to any target.
- Attach to the HTTP client the suite uses so a test cannot bypass it by building its own client.

**Interfaces:** an HTTP client hook and a database-connection check, both used by the Track B Suite and the Scanner
Adapters' target selection.

## C4. Synthetic Seed (`seed.py`, one-shot container)

**Purpose:** populate the throwaway database with invented data that exercises every feature (PT-FR-3).

**Responsibilities**
- Generate deterministically (fixed random seed) a user, banks, accounts of each type, statements, transactions
  across categories and currencies, balances, recurring payments, duplicate candidates, and a stored Drive
  connection with fake tokens.
- Use the project's own `transactagent_db` models, so the seed follows the schema (D5).
- Use reserved non-routable names (`.test`, `.invalid`) for every identity; verify that every feature is present.

**Interfaces:** run once by the Stack Manager after health; writes only to the throwaway database.

## C5. Stub Server (`stubs/`, one container)

**Purpose:** answer, inside the internal network, everything the application would otherwise send to Google and the
models, so nothing leaves the machine (Q5 = A, Q1 = A).

**Responsibilities**
- Take the real Google and Gemini hostnames as network names (aliases) on the internal network and serve: the Google
  token and consent endpoints, the Drive file calls the application makes, Gemini generate and embedding calls,
  and the OpenAI-style chat and embedding endpoints for the `local` provider.
- Generate a throwaway certificate authority and server certificate on start, and publish the authority's public
  certificate to a named volume that the API, the worker and the runner mount read-only (Q1 = A).
- Be scenario-driven: a control interface, reachable only by the runner, selects the reply (normal, hostile text,
  oversized, malformed, slow, error) for each test, and records every request it received so tests can assert
  what the application sent.
- Fail closed and be recorded: a library that ignores the certificate setting is a documented limitation, found
  by the U1 spike, not a silent gap.

**Interfaces:** HTTPS on the standard port under the Google and Gemini names; plain HTTP control interface on its own
service name.

## C6. Track B Suite (`suite/`)

**Purpose:** the executable penetration tests against the throwaway stack (PT-FR-5), run inside the runner.

**Responsibilities**
- One module per area: authentication, authorisation and object handling, input handling, CORS and cross-site
  requests, error and information leakage, Drive connection, settings/backup/export, web app (real browser),
  containers and network (static, over the real compose file and Dockerfiles), model-facing paths (stubs),
  bounded resource exhaustion, and the egress proof.
- Shared fixtures: guarded client, real sign-in, token minting for tamper tests (D6), the fixed caps (request
  counts, time limits, sizes), stub scenario control, database oracle (read-only checks that a state changed or
  did not).
- A catalogue mapping each test to its area and to the OWASP API Security Top 10 / ASVS item, so coverage is
  reportable.
- A `finding` marker that binds a test to a finding id and makes it `xfail(strict=True)` while the finding is open
  (D7).

**Interfaces:** pytest, run by the Run Orchestrator; results written as machine-readable run results.
The browser is the one shipped in the Playwright Python image used as the runner (Q2 = B).

## C7. Scanner Adapters (`scanners/`)

**Purpose:** run OWASP ZAP and Trivy and turn their output into candidates (PT-FR-6).

**Responsibilities**
- ZAP: baseline scan and an API scan driven by the API's own OpenAPI document with a valid synthetic token, as a
  container on the internal network, pinned by digest, with its own update checks off and a time limit.
- Trivy: the vulnerability database refresh as a **separate, announced download** into a named volume; then offline
  scans (`--network none`) of the saved image tarballs, the repository tree and the rendered Helm chart.
- Normaliser: map each scanner result to a `needs_validation` candidate carrying the scanner's own rule id, tool
  version and image digest; never `confirmed` (D10).

**Interfaces:** called by the Run Orchestrator; output consumed by the Findings Register.

## C8. Findings Register and Validator (`register.py`, `schema.json`)

**Purpose:** the single record of what was found and how sure we are (PT-FR-7).

**Responsibilities**
- Hold `findings.json`: one record per finding with the fields PT-FR-7 lists; states `confirmed`,
  `needs_validation`, `rejected`, `hardening_note`; severity only on `confirmed`.
- Enforce the evidence rule: a record becomes `confirmed` only if its bound test ran as an expected failure
  (not an unexpected pass) in a run against a recorded, unmodified commit.
- Validate: schema; cited files and lines exist; states consistent; test binding in both directions; every
  high or critical finding carries the date the owner was told (A2); no real data (calls the Leak Check).
- Report the funnel: candidates, confirmed, rejected, needs validation, hardening notes.

**Interfaces:** read and written by the Audit Kit, the Normaliser and me; read by the Report Generator and the
Run Orchestrator.

## C9. Audit Kit (`audit/`)

**Purpose:** Track A, the code audit adopted from the Cloudflare method (Q10 = A), with capped sub-agents
(Q11 = B, A1).

**Responsibilities**
- `PROCEDURE.md`: the six phases (reconnaissance, coverage-led hunting, disproof, structured findings, record
  verification, report) written for this repository; nothing third-party is installed or run.
- Coverage ledger: units to hunt, grouped, with status, wave and how many candidates each produced; shallow
  results are marked shallow, not clean.
- Work packages: plain files containing the group, the source paths, the procedure and the output format and
  nothing else (no live address, no `.env`, no credentials). Sub-agents write candidate files to their own scratch
  folder; I read them and write the register.
- Run budget: counts every sub-agent run against the caps (12, 6, 30, 4; hard ceiling 60) and refuses to go over
  without the owner.

**Interfaces:** produces candidates for the Findings Register; produces work packages read by sub-agents.

## C10. Leak Check (`leakcheck.py`)

**Purpose:** make the public-repository rule a test (D12).

**Responsibilities**
- Scan `pentest/`, the register, the report and the audit entries for real data.
- Take its patterns from a git-ignored local file; fail closed, with an explanation, if that file is absent.
- Report only the pattern number, file and line of a hit, never the matched text, so a hit cannot be repeated into
  a log or a chat by accident.

**Interfaces:** used by the Validator, by the Run Orchestrator before writing a report, and by me before every
commit.

## C11. Report Generator (`report.py`)

**Purpose:** `REPORT.md` and the supporting tables (PT-FR-8), generated from the register and the ledger.

**Responsibilities**
- Method, scope, coverage by area and by ledger group, findings by severity, hardening notes, residual risk,
  limitations (including every stub limitation from the spike).
- Record what was tested: commit, image digests, tool versions, caps used, sub-agent runs used, funnel.
- Never hand-edited; regenerated on every run.

## C12. Run Orchestrator (`orchestrator.py`, `cli.py`)

**Purpose:** the one command (PT-FR-9): `python -m pentest run`.

**Responsibilities**
- Run the phases in a fixed order with time limits; always tear down.
- Before a local run: read the Docker health of the five live containers and the machine's free memory, and refuse
  if they are not as required (Q3). A local run also requires an explicit "live stack is quiet" confirmation; I ask
  the owner before each full local run (Q3 = C). CI has no live stack and skips this.
- Distinguish exit statuses: success; tests failed unexpectedly; harness refused to run.

**Interfaces:** the entry point for the owner, for me and for the CI workflow.

## C13. Live Exposure Check (`live_check.py`, separate)

**Purpose:** the single, small look at the live deployment from a neighbour's point of view (PT-FR-10, A5).

**Responsibilities**
- Send only GET and OPTIONS, only allowlisted paths, no credentials, at most 20 requests.
- Take the target address at run time; never store it in the repository.
- Print what a neighbour could see: which ports answer, which paths answer without sign-in, headers, banners.

**Interfaces:** its own gate; shares no code path with the Request Guard (D13). Runs only after the guard's tests
pass, and only after the owner has been told.

## Throwaway stack services (the target and its support)

| Service | Image source | Notes |
|---|---|---|
| database | PostgreSQL 16, pinned digest | named volume; marker set by C1 |
| vector-db | Qdrant, pinned digest (the live file uses `latest`) | named volume |
| api-service | built from the checkout with the real Dockerfile | CA volume mounted, certificate environment settings |
| ingestion-worker | built from the checkout with the real Dockerfile | CA volume mounted, certificate environment settings |
| frontend | built from the checkout with the real Dockerfile | reached by service name only |
| stubs | built from `pentest/stack/` | C5 |
| seed | built from the checkout and `pentest/` | one-shot |
| runner | official Playwright Python image, pinned by digest (Q2 = B); the harness is added on top | runs C3, C6; exact reference and size stated before the first pull |
| zap | official ZAP image, pinned by digest (U3) | on the internal network; exact reference and size stated before pulling |
| trivy | official Trivy image, pinned by digest (U3) | `--network none`; database refresh is a separate announced step |

All services use the one internal network of the project. Nothing is published to the host.
