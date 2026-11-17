# Application Design Plan — Penetration Test

Role: software architect, identifying the components, interfaces, services and dependencies of the test
harness. Scope: the new `pentest/` project only. No existing application component changes (execution plan,
"Change type for every existing component: none").

Status: **four questions need your answers** (section 3). The rest is decisions I made and explain (section 2),
in the same way earlier application-design plans here did. Nothing has been built.

## 1. What I looked at before writing this

Facts from the code that shape the design (each was checked, not assumed):

- The categorisation and embedding model paths take a base URL from the environment
  (`OPENROUTER_BASE_URL`, `EMBEDDING_BASE_URL`), so a stub can stand in by configuration alone.
- The Gemini client (`genai.Client`) and the Google sign-in and Drive code use fixed Google hostnames
  (`oauth2.googleapis.com`, `accounts.google.com`, `generativelanguage.googleapis.com`) with no base-URL
  setting. A stub therefore cannot be reached by configuration alone. See Question 1.
- The API serves `/docs`, `/redoc` and the OpenAPI document (FastAPI defaults), so the sign-in sweep can be
  driven from the API's own description of itself.
- Docker only publishes a port from a container that is on a network with a gateway. A network with no route
  out (the "internal" kind, ground rule 6) publishes nothing to the host. See Question 4.
- The repository already has a nightly end-to-end workflow that builds and starts the stack in CI, and a
  Playwright setup for the frontend (TypeScript, in `frontend/e2e`). No Playwright browser is installed on this
  machine today (the browser cache is empty). See Question 2.
- The live stack shares one Docker engine with whatever I start. OrbStack has hung twice on this machine
  (recorded in memory), and an earlier second Postgres crashed the live database. See Question 3.
- Trivy needs its vulnerability database, which it downloads from the internet at run time; a network with no
  route out cannot do that. Decision D9.

## 2. Design decisions made and explained (not asked)

Each is a technical call with one defensible answer given what is above and the approved requirements.

| # | Category | Decision | Why this is not a question |
|---|---|---|---|
| D1 | Component identification | Twelve components, in one new top-level project `pentest/` with its own `pyproject.toml` and lockfile (the same layout every other Python unit here uses): **Stack Manager**, **Compose Linter**, **Request Guard**, **Synthetic Seed**, **Stub Server**, **Track B Suite**, **Scanner Adapters**, **Findings Register** (with **Validator**), **Audit Kit** (Track A procedure, ledger, work packages), **Leak Check**, **Report Generator**, **Run Orchestrator** (the one command), plus the separate **Live Exposure Check**. Components are listed in `components.md`. | The split follows the requirements one to one (PT-FR-1 to PT-FR-10); each has a different reason to change and its own tests. |
| D2 | Layout | `pentest/stack/` (compose project and the runner, stub and seed images), `pentest/src/pentest/` (the library), `pentest/tests/` (tests *of the harness*: guard, linter, seed, stubs, normaliser, validator), `pentest/suite/` (the Track B tests *against the stack*), `pentest/audit/` (procedure, ledger, work-package prompts, schema), `pentest/live_check.py`. Findings and the report live in `aidlc-docs/construction/pentest/` as required. | Keeps "tests of the test" apart from "the penetration test", so a harness test can never be mistaken for a finding. |
| D3 | Two guards, not one | **Compose Linter** (host side, before anything starts) reads the output of `docker compose config` and refuses unless: the project name is not the live one; there is no `container_name`; there is no bind mount at all (named volumes only); no `./data` path; every network is internal or the stack's own; no host-published port (see Question 4); no volume or network marked `external`; no `network_mode: host`; no mounted Docker socket; every image is pinned. **Request Guard** (inside the runner, on every request) sends only to an allowlist of the throwaway project's own service names, and independently refuses the live host names, ports and database names, and any database lacking the synthetic marker. | The allowlist is the strong control; the live-name denylist is the second, independent one, which is what ground rule 3 asks for. |
| D4 | Synthetic-data marker | The Stack Manager sets a comment on the throwaway database at creation (`COMMENT ON DATABASE ... 'pentest-synthetic'`); the guard reads it and refuses without it. All seeded identities use reserved non-routable names (`.test`, `.invalid`). | The marker does not depend on the application schema, so a future migration cannot remove it. |
| D5 | Seed | Deterministic generator (fixed random seed) run once in a one-shot container built from this repository, using the project's own `transactagent_db` models, so the seed stays valid when the schema changes. Covers every feature in PT-FR-3. | Reusing the models avoids a second copy of the schema, the very drift the project's migration comments warn about. |
| D6 | Tokens in tests | Tests sign in through the real login route for ordinary use, and mint their own tokens with the generated secret only for the tamper, expiry and wrong-key tests. The secret exists only in the run's memory and the stack's environment. | Needed to craft forged and expired tokens; harmless because the secret is generated per run. |
| D7 | Findings Register | One JSON file, `findings.json`, validated by a Python validator against a schema (the fields of PT-FR-7). The report and any tables are generated from it, never hand-edited. Each confirmed finding names a pytest test; the test carries a marker with the finding id and is `xfail(strict=True)` while the finding is open. The validator checks both directions: every confirmed finding has a marked test, and every marked test has a finding. It also checks cited paths and line numbers exist. | One source of truth; strict expected-failure makes a fix or a regression visible, as PT-FR-7 requires. |
| D8 | Run Orchestrator | One Python command (`python -m pentest run`), phases in fixed order: preflight (linter, guard self-test) → build → up → seed → isolation proof → Track B → scanners → normalise → validate → report → teardown. Teardown is in a `finally` and removes volumes. Each phase has a time limit and the run has an overall one. Exit status distinguishes "tests failed" from "harness refused to run". | Matches PT-FR-9 and PT-NFR-4. |
| D9 | Scanner Adapters | **ZAP** runs as a container on the internal network, pinned by digest, with its own update checks turned off. **Trivy** never touches the stack's network: the host exports the built images with `docker save`, and Trivy scans the tarballs, the repository tree and the rendered Helm chart with `--network none`. Trivy's vulnerability database is refreshed in a **separate, announced download step** into a named volume, and the scan itself runs offline. ZAP's exact flags are verified against the pinned image's `--help` in U3, not taken from memory. | Keeps the isolation claim true for both scanners (nothing scans with a route out), and keeps every download visible to you before it happens. |
| D10 | Normaliser | Scanner output (ZAP's JSON, Trivy's JSON) becomes `needs_validation` records with the scanner's own rule id, never `confirmed`. A scanner result is promoted only the same way as any candidate: by a failing proof test. | Same standard of evidence for every source (PT-NFR-5). |
| D11 | Audit Kit (Track A) | Procedure written into `pentest/audit/PROCEDURE.md` (the six phases, adopted from the Cloudflare method, nothing installed). Work packages are plain files: the ledger group, source paths, the procedure and the output format, and nothing else. Sub-agents write candidate files to their own scratch folder; I read them and write the register. Hunters and verifiers are different models (execution plan). | Keeps sub-agents read-only and credential-free by construction, and keeps the register under my control and the validator's. |
| D12 | Leak Check | A scan, run before every commit and in the orchestrator, that looks for real data in `pentest/`, the report and the register. Its patterns come from a git-ignored local file, because the real values must not be written down in this public repository to be matched against. If the file is absent the check fails closed with an explanation rather than passing silently. | Turns the public-repository rule into a test rather than a habit. |
| D13 | Live Exposure Check | A separate script with its own gate: GET and OPTIONS only, an allowlist of paths, no credentials, a hard cap of 20 requests, and the target address supplied at run time (never written in the repository). It shares no code path with the throwaway-stack guard, so one cannot weaken the other. | Required by A5; separate so the one place that talks to the live stack is small enough to read in a minute. |
| D14 | CI | `.github/workflows/pentest.yml`, `workflow_dispatch` only, runs the same command on a hosted runner, needs no secrets, fails on any unexpected failure or on a high or critical finding not in the register. | PT-FR-9 as approved. |
| D15 | Interfaces | Python modules with typed functions, no network API of their own. Host to Docker by the `docker` command line (as the rest of this repository does); runner to stack over the internal network by service name. | The harness has no users but you and CI. |

## 3. Questions

Please fill in the letter after each `[Answer]:` tag. Each question ends with my recommendation.

### Question 1
The application talks to Google and Gemini at fixed hostnames, with no setting to point it elsewhere. How
should the throwaway stack answer those calls, so the model-facing paths and the Drive sign-in callback can be
tested end to end without anything leaving the machine and without changing the application?

A) One stub container that takes the real Google and Gemini hostnames as names on the internal network, with a
   throwaway certificate authority generated for each run and handed to the API and the worker by environment
   setting (`SSL_CERT_FILE` and the equivalents for the libraries involved). The application images and code
   are untouched. If a particular library ignores the setting, that one path falls back to "calls fail
   closed" and is recorded as a limitation. A short spike in U1 proves which libraries honour it before the rest
   is built on it.

B) No stub for those hostnames. Calls to them simply fail because the network has no route out. We still test
   everything on our side (what is sent, what the failure handling does, state checks on the callback), but
   not what the application does with a successful reply, so a hostile model reply and a successful Drive
   connection are untested end to end.

C) Build derived images that add a small test-only patch redirecting those calls to the stub. Simplest for the
   stub, but the images under test are no longer the ones that ship, which weakens "proven against the unmodified
   code".

X) Other (please describe after [Answer]: tag below)

Recommendation: A.

[Answer]: 

### Question 2
Some web-app checks need a real browser (does injected text run as a script, can the app be framed, where the
token ends up, how a cross-site page behaves). No Playwright browser is installed on this machine today, so
this is a download. How should it be provided?

A) Install Chromium inside the test runner's own image at build time with Playwright's installer, so the browser
   runs headless on the internal network. One-time download of roughly 150 to 250 MB (I will state the exact
   figure before building), cached afterwards, and it never reaches your own browser or profile.

B) Use the official Playwright Python image, pinned by digest, as the runner. Larger (on the order of 1.5 GB;
   exact reference and size stated before pulling), fewer moving parts to maintain.

C) No real browser. Web-app items are tested over HTTP (headers, the built bundle, where the source stores the
   token) and by reading the code. Nothing to download, but "does it execute" and "can it be framed in a real
   browser" cannot be shown, so those would stay `needs_validation`.

X) Other (please describe after [Answer]: tag below)

Recommendation: A.

[Answer]: 

### Question 3
The throwaway stack and the live stack share one Docker engine on this machine. The bounded resource-exhaustion
tests you approved, the scanner and a second database all compete with the live database for memory and CPU,
and OrbStack has hung twice here. How much should the harness protect the live stack?

A) Hard CPU, memory and process limits on every throwaway container; the exhaustion tests run with fixed
   request caps; and the run refuses to start unless all five live containers report healthy and the machine has
   a stated amount of free memory. The check uses Docker's own health status only, not the live application.

B) Limits on every throwaway container, but no pre-run check.

C) A, and I also ask you before each full local run, so you can pick a quiet moment (for example when no
   ingestion is running). The CI run is unaffected.

X) Other (please describe after [Answer]: tag below)

Recommendation: C for the first full runs, then A once you trust it. If you want one answer: C.

[Answer]: 

### Question 4
Approved ground rule 1 says the throwaway stack's ports are bound to `127.0.0.1` on a range the live stack
does not use. Building the design showed a conflict: Docker cannot publish a port from a network that has no
route out (ground rule 6). Keeping loopback ports would mean giving the stack a second, ordinary network.
Which do you want?

A) **Publish no ports at all.** The runner, the browser and the scanners are all containers on the internal
   network and reach the stack by service name. The stack has no route out and no door in from the host. "Which
   ports does the real deployment publish?" is answered by reading the real `docker-compose.yml` (a static test)
   and by the live exposure check, not by the throwaway stack. This replaces the loopback-port wording in
   PT-FR-1 and ground rule 1; everything else in them stays.

B) **Publish the frontend and API on loopback** in a range the live stack does not use, through one small
   forwarder container that sits on both the internal network and an ordinary network, so you can open the
   throwaway app in your own browser by hand. The stack's own services still have no route out, but the
   forwarder does, and it is one more component whose configuration must be right.

X) Other (please describe after [Answer]: tag below)

Recommendation: A. It is the smaller and stricter design, and nothing in the test needs a door from the host.

[Answer]: 

## 4. Execution checklist

Steps of this stage. Ticked as done.

- [x] Read the execution plan, requirements, existing application-design documents and the code facts in section 1
- [x] Write this plan with decisions (section 2) and questions (section 3)
- [ ] Owner answers the four questions
- [ ] Analyse the answers for ambiguity; ask follow-ups if any
- [ ] Generate `aidlc-docs/inception/application-design/penetration-test/components.md`
- [ ] Generate `.../penetration-test/component-methods.md` (signatures only; rules come in Functional Design)
- [ ] Generate `.../penetration-test/services.md` (the Run Orchestrator and its phases)
- [ ] Generate `.../penetration-test/component-dependency.md` (matrix, communication patterns, validated diagram and a text alternative)
- [ ] Generate `.../penetration-test/application-design.md` (consolidated)
- [ ] Validate completeness and consistency against PT-FR-1 to PT-FR-11 and PT-NFR-1 to PT-NFR-8
- [ ] Log the approval prompt, present the completion message, wait for approval
- [ ] Mark Application Design complete in `aidlc-state.md`

The existing `application-design/*.md` files describe the product and are not edited. The pen-test design goes
in its own subdirectory so the product's design record stays intact.
