# Penetration Test — Requirements

Status: awaiting the owner's approval (Requirements Analysis gate). Nothing described here has been built.

## 1. Intent analysis

| Item | Value |
|---|---|
| User request | "Let's design and implement a penetration test for this application." (2026-11-17), then "Also consider https://github.com/cloudflare/security-audit-skill ... And glasswing, that derived from this." |
| Request type | New capability: a repeatable security assessment (test harness, scanners, code audit, report). No change to product behaviour. |
| Scope estimate | System-wide: API Service, Ingestion Worker, Frontend SPA, Database, containers and network, Helm chart. |
| Complexity | Complex and high-risk: the live application holds real bank data and is reached from the internet over a VPN. |
| Depth | Comprehensive, with traceability to the owner's answers (section 3). |
| Extensions | Unchanged: Security Baseline No, Property-Based Testing Partial, Resiliency Baseline No. |

## 2. Approach in one paragraph

Two tracks feed one findings register. **Track A, code audit:** follow the method of Cloudflare's
security-audit skill (reconnaissance, coverage ledger, coverage-led hunting, disproof by a separate
verifier, structured findings, independent record verification, report), adopted as a written procedure
in this repository, with nothing third-party installed. **Track B, live-behaviour test:** an executable
suite plus two open-source scanners (OWASP ZAP, Trivy), run against a throwaway copy of the stack on an
internal-only network with synthetic data. A Track A candidate becomes `confirmed` only when a Track B
proof-of-concept fails against the unmodified code. The live stack is never attacked.

## 3. Owner decisions (from penetration-test-questions.md)

| Q | Answer | What it means for the test |
|---|---|---|
| 1 | B | Throwaway stack is the target. Plus one small read-only exposure check of the live stack (unauthenticated GET and OPTIONS only, no credentials, no writes). |
| 2 | A to F; "live app reached via a VPN from internet" | Attackers: network neighbour, internet, malicious web page, malicious PDF, stolen token or config, compromised dependency or image. The VPN is treated as a network an attacker may sit on (see A3). |
| 3 | G | All areas in scope: API, web app, containers and network, Drive connection, settings/backup/export, Helm chart. |
| 4 | B | Own suite plus OWASP ZAP and Trivy from pinned Docker images. This is the owner's yes to pull those two images (exact references and sizes are stated before pulling). |
| 5 | A | Model-facing paths tested on our side only, with local stubs. Nothing leaves the machine. |
| 6 | A | Bounded resource-exhaustion checks allowed, on the throwaway stack only, with fixed caps. |
| 7 | A | Findings are recorded in the repository (`aidlc-docs/`) as they are produced. See A2 for one ordering rule. |
| 8 | "A first, then C once you have read the report" | Report only. Fixes follow in a later stage, and only those that do not change how the application is used without asking. |
| 9 | B | One command on this machine, plus a GitHub Actions workflow started by hand. No schedule. |
| 10 | A | Adopt the Cloudflare skill's method as a procedure in this repository; install nothing. |
| 11 | B | Sub-agents allowed for this task only, for the hunt and verification phases. See A1. |
| 12 | A | Glasswing not applicable; proceed with the models available in this session. |

## 4. Assumptions the owner is asked to confirm or correct

These are my readings of the answers. They are not questions; approval of this document confirms them.

- **A1. Sub-agents (Q11 = B).** Sub-agents are used only for Track A hunting and verification, only for this
  task, and only after the planning stage fixes their number. Your standing rule (no sub-agents) applies
  again when the final report is approved. They get read access to the source only: no live-stack
  address, no `.env`, no credentials. Verifier agents run on a different model from the hunters where one is
  available, which is the cross-model check the write-up recommends. The number of sub-agent runs is
  capped, and the count is reported. **If you have a spending limit, say what it is.**
- **A2. Disclosure order (Q7 = A).** Findings are written in the repository as they are produced, as you
  chose. One ordering rule is added: a finding I rate **high or critical** is told to you in chat before it
  is committed or pushed, because the live application is reachable from the internet over a VPN. This
  does not change where findings are recorded. Say if you do not want it.
- **A3. The VPN (Q2).** The VPN product and its configuration are out of scope: they are not in this
  repository and cannot be tested on a throwaway copy. A peer on the VPN is treated as a network
  neighbour, so exposure to such a peer (published ports, plain HTTP, token lifetime) is in scope. An
  attacker who has no VPN access cannot reach the application directly unless a port is forwarded; if
  one is, tell me, because that changes severity ratings.
- **A4. Helm chart (Q3 F).** Tested statically: render the chart, scan the rendered output and the chart
  with Trivy, and review it. No cluster is created.
- **A5. Live exposure check (Q1 = B).** Run once, from this machine, against the live stack's loopback
  ports and this machine's own LAN address, at most about 20 requests, from an allowlist of paths, GET and
  OPTIONS only, with no credentials. It shows what a neighbour could see; it does not test anything else.
  It runs only after the throwaway-stack guard has been tested.
- **A6. Nothing in this effort changes the product.** No `VERSION` bump, release or deployment results from
  building the test. A release happens only if the later fix stage changes the application.

## 5. Functional requirements

**PT-FR-1 Throwaway stack.** A compose definition of its own (`pentest/`), not an override of the live one:
its own project name; no `container_name` (so nothing can collide with `transactagent-*`); named volumes
only, no `./data/...` path; ports bound to `127.0.0.1` in a range the live stack does not use; an
internal-only network with no route out; a fresh database built by running the real migrations from empty;
generated JWT and database secrets; fake Google and Gemini credentials; local stubs for the Google, Gemini
and embedding endpoints. `docker compose config` is checked before anything starts. It is torn down,
volumes included, after every run.

**PT-FR-2 Safety guard.** Runs before every request and refuses to continue if the target host, port,
container name or database matches the live stack, or the database does not carry a synthetic-data marker.
The guard has its own tests, including that it refuses each live port and name.

**PT-FR-3 Synthetic data.** A seed that exercises every feature (user, banks, accounts of each type,
statements, transactions across categories and currencies, balances, recurring payments, duplicate
candidates, a stored Drive connection with fake tokens). All values are invented and generated.

**PT-FR-4 Track A, code audit.**
1. Reconnaissance: an architecture and trust-boundary document, entry points (every route, the worker's
   inputs, the OAuth callback, configuration sources) and a coverage ledger of units to hunt.
2. Coverage-led hunting in waves; each candidate states its attacker and the trust boundary crossed.
3. Disproof of each candidate by a verifier other than its author.
4. A findings register in a structured file, checked by a validator script (schema, cited paths and lines
   exist, states consistent).
5. Independent verification of the records, then the report.
Coverage gaps found by a critic pass are fed back into the ledger. Runs that find nothing are noted as
shallow rather than treated as clean.

**PT-FR-5 Track B, executable suite** (Python, pytest, httpx; Playwright for browser checks, already used in
the project). Areas, each mapped to the OWASP API Security Top 10 and ASVS where one applies:
- Authentication: a sign-in sweep of every route from the API's own OpenAPI document; token tampering,
  wrong key, `none` algorithm, expired, missing or malformed claims; replay; a small fixed number of
  sign-in guesses; response-time and message differences between unknown and known users.
- Authorisation and object handling: identifier tampering, method and verb tampering, mass assignment.
- Input handling: injection through every query, path and body field (filters, sorting, search, free text),
  oversized and malformed values, Unicode, type confusion.
- CORS and cross-site requests: origin handling, preflight, credentialed requests, request forgery.
- Error and information leakage: stack traces, server banners, version and documentation exposure.
- Drive connection: state missing, replayed, forged; redirect target; unauthenticated use of the callback.
- Settings, backup and export: what a settings change can reach, files written or read, spreadsheet-formula
  content in the CSV export.
- Web app: script injection through stored text, where the token is kept, security headers, framing.
- Containers and network: published ports and bind addresses, services reachable from outside their
  network, container user and privileges, secrets in image layers and environment.
- Model-facing paths (stubs only): hostile content in an assistant question, in a transaction description
  and in extracted PDF text; how replies are displayed; whether any reply can cause an action.
- Bounded resource exhaustion (Q6 = A): oversized bodies, the largest page size, the largest export,
  a fixed number of rapid requests, parallel requests; stack health checked afterwards.
- Egress check: the test runner proves the stack cannot reach the outside.

**PT-FR-6 Scanners (Q4 = B).** OWASP ZAP (baseline scan and an API scan driven by the OpenAPI document with a
valid synthetic token) and Trivy (images, filesystem, and the rendered Helm chart), from pinned Docker
images, against the throwaway stack only. Scanner output is normalised into the findings register.

**PT-FR-7 Findings register.** Each record: identifier, title, state (`confirmed`, `needs_validation`,
`rejected`, or `hardening_note`), attacker, boundary crossed, evidence, the test that proves it, affected
files, impact, recommended smallest fix, fix status. Severity (informational to critical, by impact given
the stated attacker) only on `confirmed`. A candidate that is only a missing best practice is a
`hardening_note`. A proof is a test that asserts the secure behaviour and fails on the unmodified code;
tests for open findings are marked expected-to-fail in strict mode, so a fix that makes one pass is
noticed and the marker is removed, and a regression turns the run red.

**PT-FR-8 Report.** `REPORT.md` (method, scope, coverage, findings by severity, hardening notes, residual
risk, limitations) with the register and coverage ledger, under `aidlc-docs/construction/pentest/`.

**PT-FR-9 One command and CI (Q9 = B).** A single command builds the stack, seeds it, runs the guard, Track
B and the scanners, writes the report, and tears everything down. A GitHub Actions workflow, started by
hand only, does the same and fails on any unexpected failure or a new high or critical finding that is not
in the register. It needs no secrets.

**PT-FR-10 Live exposure check (Q1 = B).** A separate, opt-in script that sends only the allowlisted
read-only requests described in A5 and prints what it saw.

**PT-FR-11 Fix stage (Q8).** After the report is read: triage with the owner, then fixes that do not change
how the application is used, one pull request per fix group, each with a regression proof; anything that
changes use (for example restricting access, limiting sign-in attempts, or changing how a phone connects)
waits for the owner's decision.

## 6. Non-functional requirements

- **PT-NFR-1 Live-system safety.** No request goes to the live stack except PT-FR-10. No real data, key or
  token enters the throwaway stack, the repository, a pull request, an issue or the audit log.
- **PT-NFR-2 Isolation.** No network route out of the throwaway stack; verified by a test, not assumed.
- **PT-NFR-3 Reproducibility.** Pinned image digests and package versions; deterministic seed; the report
  records versions and the commit tested.
- **PT-NFR-4 Bounded effort.** Fixed caps on request counts and run time per test; a cap on sub-agent runs;
  scanners with time limits.
- **PT-NFR-5 Evidence quality.** Proof against unmodified code; a verifier other than the author;
  defence-in-depth gaps kept separate from vulnerabilities; the funnel (candidates, confirmed, rejected,
  needs validation) reported rather than a claim of completeness.
- **PT-NFR-6 Maintainability.** The suite is its own project under `pentest/` with its own dependency file,
  documentation and tests for the guard and the seed.
- **PT-NFR-7 Disclosure order.** As A2.
- **PT-NFR-8 Process.** Branch and pull request for all work; merge only when asked; audit and state files
  updated as the work proceeds; agent identity checked before every write.

## 7. Out of scope

Fixing findings (until triage); the VPN product; Google and Gemini infrastructure; the real Gemini model
(Q5 = A); installing or running the Cloudflare skill itself or any Glasswing model (Q10 = A, Q12 = A);
denial-of-service against the live stack; testing with real data; rebuilding the existing dependency
scanning (Dependabot, pip-audit, npm audit, CodeQL), which is re-checked only; physical and social
engineering; a Kubernetes cluster.

## 8. Handed to Workflow Planning

Proposed units of work, to be confirmed there: (1) throwaway stack, seed, stubs and guard; (2) Track B suite;
(3) scanners and findings normalisation; (4) Track A code audit and register; (5) report, one-command
runner and CI workflow; (6) the live exposure check. Open for planning: the sub-agent cap (A1), the unit
order, and the port range.
