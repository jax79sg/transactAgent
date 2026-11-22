# Unit of Work Plan — Penetration Test

Units Generation, Part 1 (Planning). Source: the approved execution plan (six proposed units, order U1, U2, U3,
U6, U4, U5) and the approved Application Design (components C1 to C13). User Stories were skipped, so the "story map"
artifact maps requirements (PT-FR and PT-NFR) to units instead.

Status: **three questions need your answers** (section 3). The rest is decomposition decisions I made and explain
(section 2). Nothing has been built.

## 1. What this stage had to resolve

The execution plan's six units were drawn before the components were designed. Mapping the thirteen components onto
them showed one problem and a few details:

- **A dependency the plan did not show.** The Findings Register (C8) and the Leak Check (C10) were placed in U4, the
  last big unit. But U2 (the baseline suite) and U3 (the scanners) both produce findings and candidates that have to
  be recorded, the `finding` marker in the suite points at register ids, and the Leak Check is needed from the first
  commit of a public repository. They cannot wait for U4. See Question 1.
- **The orchestrator (C12) grows across units.** It cannot be built whole in one unit, because most of its phases
  call things built later. Decision U-D3.
- **Several units are blocked on a person, not on code:** the first image pull (U1), the scanner pulls and database
  refresh (U3), the live check (U6) and the sub-agent waves (U4) each need a statement or an answer from the owner.
  The order and the pause points are in U-D4.

## 2. Decisions made and explained (not asked)

| # | Topic | Decision | Why this is not a question |
|---|---|---|---|
| U-D1 | Unit boundary rule | A unit is one pull request that adds a working, tested slice of `pentest/` and can be reviewed alone. Every unit ends with its own tests passing and the leak scan clean. | This is how every earlier unit in this repository was delivered. |
| U-D2 | Harness tests in ordinary CI | `pentest/tests/` (tests *of the harness*: guard, linter, register, leak check, normaliser, report) are pure Python with no Docker, so they run on every pull request in a normal workflow, `test-pentest.yml`, like the other units' `test-*.yml`. This is separate from the hand-started pen-test workflow (`pentest.yml`, U5), which needs Docker and images. | The harness must not rot between runs, and its own tests cost almost nothing. |
| U-D3 | The orchestrator grows phase by phase | U1 creates the Run Orchestrator with the phases it can run (preflight, build, up, seed, isolation, teardown); U2 adds the suite phase; U3 the scanner and normalise phases; U4 the validate phase's real inputs; U5 the report phase, the final exit statuses and the CI workflow. Each unit leaves the one command working end to end for the phases that exist. | An orchestrator built last could not be exercised until the end; growing it keeps every unit verifiable on a real run. |
| U-D4 | Where a unit stops for the owner | U1: before the first image pull (exact reference, digest, size). U3: before each scanner pull, and separately before Trivy's database refresh. U6: before the one live run (announced). U4: after wave 1 (usage report, ask before wave 2) and before any finding rated high or critical is committed (A2). Every local full run: ask first (design Q3 = C). | These are the owner's standing conditions from the approved requirements and design answers. |
| U-D5 | Functional Design and Infrastructure Design per unit | As in the execution plan, adjusted for the Question 1 outcome (section 4). Infrastructure Design: U1 (compose project, network, volumes, limits, images), U3 (scanner images and their network), U5 (the workflow). | Unchanged from the approved plan apart from where the register's design lands. |
| U-D6 | Test of "unmodified code" | Every unit that adds a proof records, with the run, the commit and whether the application source directories were clean (Stack Manager's `BuildRecord`). Application source is never edited by a pen-test unit; the fix stage (later, its own plan) is the only place it can change. | Requirement PT-NFR-5 and the plan's quality gates. |
| U-D7 | Code organisation | Brownfield addition: everything under `pentest/` (layout in `components.md`), reports under `aidlc-docs/construction/pentest/`, one workflow file per purpose. No product directory changes. | Already fixed by the design. |

## 3. Questions

Please fill in the letter after each `[Answer]:` tag. Each question ends with my recommendation.

### Question 1
The Findings Register (C8) and Leak Check (C10) are needed before U2 and U3, not in U4 where the approved plan put
them. Where should they go?

A) **Add a small first unit, U0 "Evidence core"**, before U1: the project skeleton (`pyproject.toml`, lockfile, the
   ordinary-CI workflow of U-D2), the register with its validator, and the Leak Check. Pure Python, no Docker, no
   images, no risk to the live stack, quick to review. U1 to U6 stay as approved; U4 keeps the code audit
   (procedure, ledger, hunting, proofs). Seven units, order U0, U1, U2, U3, U6, U4, U5.

B) **Keep six units and put the register and Leak Check in U1.** Fewer pull requests, but U1 (stack, seed, stubs,
   guard, linter, orchestrator start) becomes much larger and mixes Docker work with pure Python.

C) **Keep six units and build the register in U3** (with the normaliser). Findings from U2 are held in a plain
   scratch list until then, and the Leak Check is built in U1. Smallest change to the approved plan, but U2's
   findings are not recorded in the register as they are produced, and the two-way test binding is checked late.

X) Other (please describe after [Answer]: tag below)

Recommendation: A.

[Answer]: 

### Question 2
There will be six or seven unit pull requests plus the inception one, each building on the last. Merging is yours
to ask for. How should the branches be arranged?

A) **Sequential:** each unit's branch starts from `main`. I do the design stages for the next unit while a pull
   request waits, but I do not start its code until you have merged the previous one. Cleanest history, and you
   control the pace; slower if merges wait.

B) **Stacked:** each unit's branch starts from the previous unit's branch and its pull request targets that
   branch; you can merge them in order whenever you like and I never wait on a merge. GitHub retargets each pull
   request to `main` when its base is merged. The inception branch is already stacked this way on the
   release-record pull request (#77).

X) Other (please describe after [Answer]: tag below)

Recommendation: B. Units depend directly on each other's code (U2 needs U1's stack), so waiting on each merge would
stall the work, and a stacked set can still be merged one at a time.

[Answer]: 

### Question 3
The project workflow stops for your approval at every stage of every unit: functional design, infrastructure design,
the code plan, and the finished code. With seven units that is about 23 stops (5 functional designs, 3 infrastructure
designs, 14 code plan and code stops, and Build and Test). Do you want them all?

A) **Every stop, as the workflow says** (about 23). Maximum control; each stop is a short message.

B) **One stop for design and plan, one for the code**, per unit: the unit's Functional Design, Infrastructure Design
   and code plan are presented and approved together, and the finished code still stops on its own. About 15 stops.

C) **Design stops only where something is decided that you may disagree with** (a threshold, a download, a safety
   rule, a trade-off); routine design stages are written, logged and shown in the next message, and every code stop
   stays. The audit log still records everything. About 10 to 14 stops, depending on what turns up.

X) Other (please describe after [Answer]: tag below)

Recommendation: A for U0 and U1 (the safety-critical units), then B once you have seen how they go.
If you want one answer: A.

[Answer]: 

## 4. Proposed decomposition (assumes Question 1 = A; the other options are shown beside it)

| Unit | Content (components) | Requirements | Depends on | Functional Design | Infrastructure Design |
|---|---|---|---|---|---|
| **U0 Evidence core** (new, if Q1 = A) | Project skeleton; C8 Findings Register and Validator; C10 Leak Check; `test-pentest.yml` | PT-FR-7 (register), PT-NFR-1 (leak), PT-NFR-6, PT-NFR-7 | none | EXECUTE (register schema, states, severity rubric, validator rules; leak-check rules) | SKIP |
| **U1 Harness core** | C1 Stack Manager, C2 Compose Linter, C3 Request Guard, C4 Synthetic Seed, C5 Stub Server; the stack definition and the runner, stub and seed images; Run Orchestrator start (preflight, build, up, seed, isolation, teardown) | PT-FR-1, 2, 3; PT-NFR-1, 2, 3 | U0 | EXECUTE (guard rules, linter rules, parity list, seed content, stub scenarios, the certificate spike) | EXECUTE (compose project, internal network, volumes, CPU/memory/process limits, image references and sizes) |
| **U2 Baseline Track B suite** | C6 Track B Suite; orchestrator suite phase | PT-FR-5; PT-NFR-4 | U1, U0 | EXECUTE (catalogue, caps, the OWASP/ASVS mapping) | SKIP |
| **U3 Scanners** | C7 Scanner Adapters and normaliser; orchestrator scanner and normalise phases | PT-FR-6 | U1, U0 | EXECUTE (normaliser mapping) | EXECUTE (ZAP and Trivy images, ZAP flags, Trivy database refresh) |
| **U6 Live exposure check** | C13 Live Exposure Check | PT-FR-10; A5 | U1 (guard tested) | SKIP | SKIP |
| **U4 Track A code audit** | C9 Audit Kit; the audit run (reconnaissance, waves, disproof, proofs added to the suite, record verification) | PT-FR-4; A1 | U0, U1, U2, U3 | EXECUTE (audit procedure, ledger, work-package format, budget rules) | SKIP |
| **U5 Report, runner, CI** | C11 Report Generator; Run Orchestrator completion (report phase, exit statuses); `pentest.yml` | PT-FR-8, 9; PT-NFR-3 | all | SKIP | EXECUTE (the hand-started workflow) |

If Question 1 = B: no U0; U1 also takes C8 and C10, the skeleton and `test-pentest.yml`; its Functional Design also
covers the register. If Question 1 = C: no U0; U1 takes the skeleton, `test-pentest.yml` and C10; U3 takes C8 and its
Functional Design; U2's findings wait in a scratch list.

Execution order if Q1 = A: **U0, U1, U2, U3, U6, U4, U5**, then Build and Test. (Otherwise the same without U0.)

## 5. Execution checklist

- [x] Read the approved execution plan, requirements and application design; map components to units
- [x] Write this plan with decisions (section 2), questions (section 3) and the proposed decomposition (section 4)
- [ ] Owner answers the three questions
- [ ] Analyse the answers for ambiguity; ask follow-ups if any
- [ ] Log the approval prompt ("Unit of work plan complete. Review the plan in aidlc-docs/inception/plans/penetration-test-unit-of-work-plan.md. Ready to proceed to generation?") and get approval
- [ ] Generate `aidlc-docs/inception/application-design/penetration-test/unit-of-work.md` (unit definitions and responsibilities)
- [ ] Generate `.../penetration-test/unit-of-work-dependency.md` (dependency matrix and order)
- [ ] Generate `.../penetration-test/unit-of-work-story-map.md` (stories were skipped: maps PT-FR and PT-NFR items to units)
- [ ] Document the code organisation (brownfield addition under `pentest/`) in `unit-of-work.md`
- [ ] Validate unit boundaries and dependencies (no cycles; every requirement and component assigned to exactly one unit)
- [ ] Update the execution plan's unit table and `aidlc-state.md`; present the completion message and wait for approval
- [ ] Open the pull request for the inception records (`security/pentest-inception`), bind it, and report

The product's existing `unit-of-work*.md` files describe the product and are not edited.
