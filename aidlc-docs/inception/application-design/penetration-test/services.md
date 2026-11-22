# Penetration Test — Services and Orchestration

Services here are the sequences that coordinate the components. They are not network services: the harness has no
API of its own (D15). Details of each rule are decided in Functional Design.

## S1. Run Service (Run Orchestrator)

One command, `python -m pentest run`, runs these phases in this order. A phase that fails stops the run, except
that teardown always runs (in a `finally`) and removes the volumes.

| # | Phase | What happens | Stops the run when |
|---|---|---|---|
| 1 | Preflight | Compose Linter on the rendered configuration; Request Guard self-test; Leak Check patterns present; for a **local** run: Docker health of the five live containers, free memory, and the explicit quiet confirmation (Q3 = C) | any violation, any guard case not refused, patterns file absent, live containers not all healthy, memory below the stated level, no confirmation |
| 2 | Build | Build images from the checkout; record digests, commit and whether the application source directories are clean | build failure; (a dirty source tree does not stop the run but is recorded, and then no finding can be `confirmed` from it) |
| 3 | Up | Start all services with their limits; wait for health; confirm the schema is at the migration head from empty | unhealthy service, wrong revision |
| 4 | Seed | Run the seed, set the synthetic marker, verify every feature has data | marker missing, a feature with no data |
| 5 | Isolation | The runner proves it, the stack and the stubs have no route out (name lookups and connections to the outside fail) and that the stubbed hostnames resolve to the stub | any route out |
| 6 | Suite | Track B in the runner, through the Request Guard, with the fixed caps; run results saved | harness error (a test that finds a weakness is a result, not a stop) |
| 7 | Scanners | ZAP baseline and API scan on the internal network; Trivy offline on the saved images, the repository and the rendered chart | scanner could not run (recorded as a limitation, not a silent pass) |
| 8 | Normalise | Scanner output becomes `needs_validation` candidates | schema error |
| 9 | Validate | Findings Validator; Leak Check over everything that will be written | any problem |
| 10 | Report | Generate `REPORT.md` from the register and the ledger | Leak Check hit |
| 11 | Teardown | Remove containers, volumes, networks; check `leftovers()` is empty | leftovers (reported loudly; exit status 2) |

Exit status: 0 success; 1 an unexpected test failure or a new high or critical finding not in the register;
2 the harness refused to run or could not clean up.

Interaction rules:
- No request leaves the runner except through the Request Guard. The scanners are pointed only at service names
  inside the project.
- Nothing is mounted from the host. Code goes in by building the images; results come out by copying from the
  finished runner container.
- CI runs the same command with `ci=True`: no live stack exists there, so the live-health and quiet checks are
  skipped, and everything else is the same.

## S2. Evidence Service (candidate to finding)

The path every candidate takes, whatever found it (Track A hunter, scanner, or a Track B test):

```
candidate (needs_validation)
   |-- disproof by a verifier other than its author -----> rejected   (reason recorded)
   |-- only a missing best practice ---------------------> hardening_note
   |-- proof test written: asserts the SECURE behaviour
          |-- test fails on the unmodified code (xfail, strict) --> confirmed (severity by impact, stated attacker)
          |-- test passes on the unmodified code --------------> rejected (it was not a weakness)
          |-- cannot be turned into a test ---------------------> stays needs_validation
```

Rules the Register enforces:
- `confirm()` needs the bound test to have failed as expected in a run whose source was recorded as clean
  and unmodified. A hunter's or a scanner's say-so is never enough.
- A high or critical finding needs the date the owner was told (A2) before the validator passes, so the order
  "tell the owner, then commit" is checked by code, not memory.
- Open findings are strict expected failures. When a fix makes the test pass, the run reports an unexpected pass;
  the marker is then removed in the fix change. A regression shows up as a normal failure.

## S3. Audit Service (Track A)

Driven by me, not by code, but constrained by the Audit Kit:

1. **Reconnaissance (me, no sub-agents):** architecture and trust-boundary notes; every entry point (routes, the
   worker's inputs, the Drive callback, configuration sources); the coverage ledger split into groups.
2. **Wave 1 hunting:** one work package per ledger group, at most 12 hunter runs (Sonnet 5.5), read-only on the
   source. Each `Candidate` states its attacker and the boundary it crosses.
3. **Pause:** the Run Budget reports runs used, approximate tokens and candidates found; I ask the owner before wave 2.
4. **Critic pass and wave 2:** gaps in the ledger become at most 6 further hunts.
5. **Disproof:** each surviving candidate goes to a verifier on a different model (Opus 5.5), at most 30 runs.
6. **Proofs:** I turn survivors into Track B tests (S2) and run them; the register records the outcome.
7. **Record verification:** at most 4 verifier runs over the register itself; then the report.
8. **Ceiling:** 60 sub-agent runs in all; `BudgetExceeded` stops and asks the owner.

Sub-agents get a work-package file and nothing else: no live address, no `.env`, no credentials, and they write only
to their own scratch folder.

## S4. Hygiene Service (public repository rules)

Applied at three points: before every commit (by me), in Validate and Report (by the orchestrator), and in CI.
- Leak Check over `pentest/`, the register, the report and the audit entries; patterns from a git-ignored local
  file; fails closed if absent; reports pattern number and location only.
- A2 disclosure order, checked by the Validator (S2).
- Agent identity (`gh api user`) checked before every write to GitHub (process rule, not code).

## S5. Live Check Service

A separate command (`python pentest/live_check.py --target ...`), not part of the Run Service. Preconditions,
checked in order: the Request Guard tests pass; the owner has been told it is about to run (A5); the target is
supplied on the command line. It sends at most 20 allowlisted GET and OPTIONS requests with no credentials and
prints what it saw. The output is summarised in the report without real addresses.
