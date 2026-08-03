# User Stories — Recategorization Review Panel

Appends **Epic 6** to the project's existing story set (`stories.md`, Epics 1–5), kept in a separate file so the original project's history stays untouched.

**Persona**: **The Account Owner** (`personas.md`) — unchanged; this feature introduces no new persona.
**Granularity**: Coarse, epic-level capability stories — matches the existing convention.
**Acceptance Criteria**: Given/When/Then happy path plus explicit edge-case scenarios — matches the existing convention.
**Traceability**: Each story references `recategorization-review-requirements.md`'s FR-RR/NFR-RR IDs. FR-RR-10 (existing single-row correction endpoint is unchanged) has no dedicated story — it's a "no new behavior" requirement, not a user-facing capability.
**Naming assumption**: the new page/nav entry is called **"Review"**; panel items are called **proposals**, per the story plan's flagged assumption — change here (and only here) if you'd prefer different wording.

---

## Epic 6: Recategorization Review

### US-6.1: Broaden the search when I correct a category
**As** the Account Owner, **I want** a manual category correction to search both unresolved (`UNSURE`) transactions and transactions that already have a category **so that** a correction can surface matches wherever they exist, not just in the `UNSURE` backlog.

**Traces to**: FR-RR-1, FR-RR-2

**Acceptance Criteria**:
- *Happy path*: Given I correct a transaction's category, When the correction saves, Then the system searches both `UNSURE` transactions and already-categorized transactions for similarity matches and records a proposal for each candidate found, capturing the candidate, the proposed category, the match score, and which bucket it came from.
- *Edge case — no candidates found*: Given no transaction is similar enough to the correction, When the search runs, Then no proposals are recorded and the original correction still saves normally.
- *Edge case — self-match excluded*: Given the transaction I just corrected, When the search runs, Then that same transaction is never proposed as its own candidate.
- *Edge case — no duplicate proposals*: Given the same candidate has already been proposed against the same correction and is still pending, When the search runs again for any reason, Then a second duplicate pending proposal for that exact candidate+source pair is not created (per NFR-RR-2).

### US-6.2: Auto-apply the clearest matches among unresolved transactions
**As** the Account Owner, **I want** extremely confident matches among my `UNSURE` transactions to be categorized automatically **so that** I don't have to review the obvious cases one by one.

**Traces to**: FR-RR-3

**Acceptance Criteria**:
- *Happy path*: Given a candidate from the `UNSURE` bucket whose match score clears the (higher) auto-apply threshold, When the search completes, Then that transaction's category is set immediately, its source is recorded as similarity-based, and no review action is required.
- *Edge case — visible after the fact*: Given a transaction was auto-applied, When I later look at the Review page, Then I can still see it listed as already-applied (not pending), so I have visibility into what changed automatically even though I didn't act on it.
- *Edge case — threshold is a Functional Design decision*: This story asserts the auto-apply/review split exists and where the line falls (UNSURE bucket only, per US-6.3); the exact numeric threshold value is set in Functional/NFR Design, not here.

### US-6.3: Never silently change a transaction that's already categorized
**As** the Account Owner, **I want** any proposed change to a transaction that already has a category **to always wait for my review**, regardless of how confident the match is, **so that** I never lose or silently overwrite a categorization I — or the system — already made.

**Traces to**: FR-RR-4

**Acceptance Criteria**:
- *Happy path*: Given a candidate transaction already has a category (from similarity, the LLM, or a prior manual edit), When a match is found for it, Then it is always recorded as a pending proposal and never auto-applied, no matter how high the match score is.
- *Edge case — near-perfect match still waits*: Given an already-categorized candidate has a very high match score (higher than the `UNSURE`-bucket auto-apply threshold from US-6.2), When the search runs, Then it is still routed to pending review, not auto-applied — the auto-apply path applies only to the `UNSURE` bucket.
- *Edge case — borderline UNSURE match also waits*: Given an `UNSURE` candidate's score is at or above the existing similarity threshold but below the new auto-apply threshold, When the search runs, Then it is recorded as pending, not silently discarded and not auto-applied.

### US-6.4: Review and act on pending proposals
**As** the Account Owner, **I want** a dedicated Review page listing every pending proposal with enough context to judge it **so that** I can approve the ones I agree with and reject the ones I don't, one at a time or in bulk.

**Traces to**: FR-RR-5, FR-RR-6, FR-RR-7

**Acceptance Criteria**:
- *Happy path*: Given at least one pending proposal exists, When I open the Review page, Then I see, per proposal, the candidate transaction (date, description, amount, current category), the proposed category, the match score/bucket, and which correction triggered it — and I can approve or reject it individually.
- *Happy path — bulk actions*: Given I select several proposals via per-row checkboxes or "select all", When I click bulk approve or bulk reject, Then all selected proposals are actioned in a single step.
- *Edge case — approval writes through*: Given I approve a proposal, When the approval is recorded, Then the candidate transaction's category is updated immediately and the proposal no longer appears in the pending list.
- *Edge case — empty state*: Given there are no pending proposals, When I open the Review page, Then it shows a clear empty state rather than an error or a blank screen.

### US-6.5: Rejected proposals leave my data untouched, with no memory
**As** the Account Owner, **I want** a rejected proposal to leave the transaction exactly as it was **so that** I never lose an existing categorization by mistake, even if the same suggestion comes up again later.

**Traces to**: FR-RR-8

**Acceptance Criteria**:
- *Happy path*: Given I reject a proposal (individually or in bulk), When the rejection is recorded, Then the candidate transaction's category is left completely unchanged and the proposal is marked rejected.
- *Edge case — no suppression memory*: Given I rejected a specific category proposal for a transaction, When a future correction generates a new match for that same transaction and category, Then it is proposed again — rejection does not permanently suppress it (per FR-RR-8, an explicit choice, not an oversight).
- *Edge case — never-reviewed proposals*: Given a proposal I neither approve nor reject, When I check the transaction later, Then its data is unaffected either way — only an explicit approval changes a transaction.

### US-6.6: See at a glance that proposals are waiting
**As** the Account Owner, **I want** to see how many proposals are waiting for review without hunting for the Review page every time **so that** I don't forget about them between sessions.

**Traces to**: FR-RR-9

**Acceptance Criteria**:
- *Happy path*: Given one or more pending proposals exist, When I am anywhere in the app, Then a count/badge showing the pending total is visible in navigation.
- *Edge case — count reaches zero*: Given every pending proposal has been approved or rejected, When I next view the app, Then the badge disappears (or shows zero, per whatever the app's existing badge convention is).
- *Edge case — auto-applied items excluded*: Given a transaction was auto-applied (US-6.2), When the pending count is computed, Then it does not contribute to the count, since it never required my action.

---

## Personas

No changes to `personas.md` — **The Account Owner** already covers this feature; there is no secondary/admin persona introduced by the review panel.
