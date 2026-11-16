# Penetration Test — Clarifying Questions

Request (2026-11-17): "Let's design and implement a penetration test for this application."

Request type: new capability (a repeatable security test), not a change to the product.
Scope estimate: system-wide (API service, web app, containers and network, Google Drive connection, model-facing paths).
Complexity: complex and high-risk, because the live application holds real bank data. Depth: comprehensive.

Please answer by filling in the letter after each `[Answer]:` tag. Where a question says "several allowed",
list every letter that applies (for example `A, C`). Each question ends with my recommendation.

## Ground rules I will follow whatever you answer

These are not questions. Say so if any of them is wrong.

1. **The live stack and its data are never attacked.** The test runs against a separate, throwaway copy of the
   stack: its own compose project name, its own named volumes, no fixed container names, ports bound to
   `127.0.0.1` on a range the live stack does not use, a fresh database, and synthetic data only (invented
   accounts, banks, merchants and amounts). The isolated-copy hazard recorded in `build-instructions.md`
   (a second Postgres on `./data/postgres` once crashed the live database) is designed out: no `./data`
   path, and `docker compose config` is checked before anything starts.
2. **No real secrets and no outbound calls.** The throwaway stack gets generated JWT and database secrets and
   fake Google and Gemini credentials. Model and Google endpoints are replaced by local stubs, so nothing is
   sent to a third party and nothing costs money.
3. **A guard refuses to run against the live stack.** The runner checks the target host, port and database
   before any request is sent, and stops if the target is the live stack (ports 7878/8787/5433, container
   names `transactagent-*`) or holds anything that is not synthetic.
4. **Nothing I commit or post contains real data.** Same rule as the rest of the repository, which is public.
5. **Extension configuration is unchanged** (Security Baseline: No; Property-Based Testing: Partial;
   Resiliency Baseline: No). This is a test of the application, not a change to how the application is built.
6. **The throwaway stack has no route to the outside.** It runs on an internal-only Docker network (no
   gateway), and the test runner is a container on that same network. This is also the "no external network"
   sandbox condition that Cloudflare's security-audit skill requires before any target code may run (see
   Question 10).
7. **A finding has to earn its place.** Following the method in Cloudflare's skill and write-up: every
   candidate states its attacker and the trust boundary it crosses (tied to your answer to Question 2); it is
   only called `confirmed` if a proof-of-concept test fails against the **unmodified** code on the throwaway
   stack; a lead that cannot be demonstrated stays `needs_validation`; a candidate that is only a missing
   best practice is a `hardening note`, not a vulnerability; and severity is given only to confirmed
   findings, by impact. The agent that proposes a finding does not get to mark it confirmed on its own say-so.

## Question 1
How should the live (real) stack be treated?

A) Never touched at all. The isolated copy is the only target. (Safest; cannot see how the live
   deployment is actually configured, only how the images behave with a fresh configuration.)

B) The isolated copy is the main target, plus a small **read-only exposure check** against the live stack:
   unauthenticated GET and OPTIONS requests only, no credentials sent, no writes, a handful of requests. It
   answers "what can another device on my network see?" for the real deployment (published ports, headers,
   which paths answer without a login). No login attempts, no fuzzing, no load.

C) Test the live stack fully. (Not recommended, and I would decline anything destructive or any login attack
   against real data.)

X) Other (please describe after [Answer]: tag below)

Recommendation: B.

[Answer]: 

## Question 2
Which attackers should the test assume? (several allowed)

A) Someone else on the same local network (another device on the home Wi-Fi, or a guest) who can reach the
   published ports.

B) Someone on the internet, because the application is reachable through a tunnel, reverse proxy, port
   forward or cloud host.

C) A malicious web page that you visit in the same browser where you are signed in (cross-site requests).

D) A malicious or tampered PDF placed in the watched Google Drive folder (for example a file shared with you).

E) A stolen or leaked sign-in token, or a stolen copy of the configuration file.

F) A compromised dependency or base image.

X) Other (please describe after [Answer]: tag below)

Recommendation: A, C, D and E at least. Add B only if the application is, or may become, reachable from the internet.

Also: how is the live application reached today? (one line, for example "this machine only", "phone over home
Wi-Fi", "through a tunnel", "in Kubernetes")

[Answer]: 

## Question 3
Which parts of the system are in scope? (several allowed)

A) The API: every route's sign-in requirement, token handling, input validation, injection, error leakage, CORS.

B) The web app: script injection, where the token is kept, security headers, framing.

C) Containers and network: which ports and services a neighbour can reach, container privileges, secrets in
   images and environment, database and vector database exposure.

D) The Google Drive connection: the consent and callback flow.

E) Settings, backups and the CSV export: configuration overrides, files written or read, spreadsheet-formula
   content in exports.

F) The Kubernetes (Helm) deployment in `deploy/helm`.

G) All of the above.

X) Other (please describe after [Answer]: tag below)

Recommendation: G. Dependency and image vulnerabilities already have a continuous scan (Dependabot,
pip-audit, npm audit, CodeQL), so they are only re-checked, not rebuilt.

[Answer]: 

## Question 4
Which tools?

A) A purpose-built test suite in the repository (Python, using packages the project already uses), covering
   the application's own routes, rules and behaviours. Repeatable, reviewable, no new downloads.

B) A, plus two well-known open-source scanners run from pinned Docker images against the isolated copy:
   **OWASP ZAP** (baseline web scan) and **Trivy** (image and configuration scan). They find different things
   from a hand-written suite. This needs pulling those two images (roughly 0.1 GB for Trivy and 1 GB for
   ZAP); I will not pull them without your yes.

C) Manual, exploratory testing only, with a written report and no repeatable suite.

X) Other (please describe after [Answer]: tag below)

Recommendation: B.

[Answer]: 

## Question 5
How should the model-facing parts be tested? These are the AI assistant (your transactions are sent to a
model together with a question) and the statement extraction path (a PDF's text is sent to a model).

A) Test **our side only**, using a local stub in place of the model: what is sent, what is trusted in the
   reply, how the reply is displayed, whether a reply can cause any action. Nothing leaves the machine.
   (Cannot show how the real model reacts to a hostile document.)

B) A, plus a **small, capped run against the real Gemini model** with synthetic documents carrying hostile
   instructions. Costs a few cents and sends synthetic text to Google. Needs a Gemini key placed in the
   throwaway stack by you; I will not handle your key.

C) Leave these out of this test.

X) Other (please describe after [Answer]: tag below)

Recommendation: A.

[Answer]: 

## Question 6
May the test include bounded resource-exhaustion checks (oversized request bodies, the largest allowed page
size, a very large export, many rapid sign-in attempts, many parallel requests), on the throwaway stack only?

A) Yes, with fixed caps (for example at most a few thousand requests, and a time limit) and the stack's
   health checked afterwards.

B) No denial-of-service style tests of any kind. Sign-in guessing is tested only with a small fixed number
   of attempts.

X) Other (please describe after [Answer]: tag below)

Recommendation: A.

[Answer]: 

## Question 7
Where should findings be recorded? The repository is **public**, so a written list of unfixed weaknesses is
readable by anyone.

A) In the repository (`aidlc-docs/`) as I go, like every other record here. (Simplest, but publishes unfixed
   weaknesses.)

B) **Kept local and uncommitted** while anything is unfixed (a git-ignored folder on this machine, and
   described to you in chat), then committed as a sanitized summary once each item is fixed or accepted.
   The test suite itself is committed; tests for a known unfixed item are marked as expected-to-fail
   with a neutral message, not a description.

C) In a private place you choose (for example a private GitHub security advisory, which needs admin rights
   that the agent account does not have, so you would create it).

X) Other (please describe after [Answer]: tag below)

Recommendation: B.

[Answer]: 

## Question 8
What should happen to what the test finds?

A) Report only. You triage, then tell me what to fix.

B) Report, and fix everything rated high or critical in this effort, each fix on its own pull request.

C) Report, and fix everything that does not change how you use the application; ask before anything that
   would (for example, blocking access from a phone over plain HTTP, or limiting sign-in attempts).

X) Other (please describe after [Answer]: tag below)

Recommendation: A first, then C once you have read the report. Some fixes are design decisions that are yours.

[Answer]: 

## Question 9
Should the test be repeatable on demand and in CI?

A) A single command on this machine that brings up the throwaway stack, runs everything, writes the report
   and tears the stack down. No CI.

B) A, plus a GitHub Actions workflow started by hand (`workflow_dispatch`) that does the same in CI and fails
   if a previously fixed item regresses.

C) B, plus a nightly schedule.

X) Other (please describe after [Answer]: tag below)

Recommendation: B. A nightly schedule is easy to add later once the suite is stable.

[Answer]: 

## Question 10
You pointed me at [cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill) (MIT
licence). It is a *source-code* audit method, six phases: map the system and its trust boundaries, hunt in
coverage-led waves, try to disprove each candidate with a fresh verifier, write structured findings
(`confirmed`, `needs_validation`, `rejected`), verify the records independently, then report. It
deliberately does **not** probe deployed systems. That is complementary to the live-behaviour test above,
not a replacement, so the plan would have two tracks: a **code audit** that produces candidates and a
coverage ledger, and the **throwaway-stack test** that turns each candidate into a repeatable proof of
concept. How should I use it?

A) **Adopt the method, install nothing.** I write the procedure into this repository's plan (phases,
   coverage ledger, the finding states and the proof-against-unmodified-code rule) and follow it myself. No
   third-party code or instructions are downloaded or run. (Loses its ready-made schema and validator.)

B) **Install the skill itself**, then run it on this repository. It installs with
   `npx skills add https://github.com/cloudflare/security-audit-skill --skill security-audit` (this
   downloads it from GitHub; it ships a Node validator script). `npx` is not on the PATH of this app
   session, so Node would have to be made available first. I would read every file in it, including the
   validator, before running anything, and it would write its output outside the repository.

C) Do not use it.

X) Other (please describe after [Answer]: tag below)

Recommendation: A. It gets the useful discipline (threat model per finding, proof against unmodified code,
separate states) without executing a third party's code, and B can still be added later.

[Answer]: 

## Question 11
The skill and Cloudflare's write-up get their quality from **independence**: a different agent than the one
that found a candidate tries to disprove it, and a different model checks the result. The skill does this
with parallel sub-agents. Your standing instruction is not to use sub-agents. How should independence be
obtained?

A) **Keep your rule.** No sub-agents. The phases run one after another in this session, and independence
   comes from things that do not depend on my own judgment: (1) every confirmed finding needs an executable
   proof that fails against the unmodified code on the throwaway stack; (2) a deterministic validator
   (schema and cited-file checks, in code) runs over the findings; (3) optionally, **you** start the
   verification pass in a separate session on a different model, which is the cross-model check the
   write-up recommends. (Weaker than parallel fresh agents for logic flaws that cannot be turned into a
   proof; those stay `needs_validation`.)

B) **Allow sub-agents for this task only**, for the hunt and verification phases, then back to your rule.
   (More coverage and more cost, and it is your explicit exception.)

X) Other (please describe after [Answer]: tag below)

Recommendation: A.

[Answer]: 

## Question 12
"Glasswing": the sources I could find describe
[Project Glasswing](https://www.anthropic.com/glasswing) as Anthropic's gated programme (introduced 7 April
2026) that gives selected organisations access to a restricted model, Claude Mythos Preview, to find and fix
vulnerabilities. It is access to a model, not a downloadable tool or skill, and I cannot invoke that model
from this session. Public coverage also describes Cloudflare's harness as following Glasswing-era work, the
reverse of "Glasswing derived from this"; treat that ordering as unverified. If you meant something else
by Glasswing, or have access through it:

A) Not applicable to this test. I proceed with the models available in this session and the checks in
   Question 11.

B) You have Glasswing (or Cyber Verification Program) access and want the independent verification pass run
   on that model. You would set up that session or key yourself; I would hand over the findings file and the
   verification instructions and would never handle the credential.

X) Other, or a link to what you meant (please describe after [Answer]: tag below)

Recommendation: A, unless you already have access.

[Answer]: 
