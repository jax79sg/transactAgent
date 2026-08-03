# Recategorization Review Panel — Clarifying Questions

Please answer each question by filling in the letter choice after the `[Answer]:` tag. If none of the options match what you want, choose the last option (Other) and describe your preference.

## Context (for reference while answering)

Today, when you manually correct a transaction's category:
- That one transaction updates immediately.
- The system also automatically re-scans every transaction still marked `UNSURE`, and silently auto-applies your correction as a category to any that look similar enough — no review, no notification, direct database write.
- Already-categorized transactions (from similarity match, the LLM, or a prior manual edit) are never touched by this sweep — only the `UNSURE` backlog.

## Question 1: What should the review panel cover?

A) Keep the scope exactly as it is today — the review gate only applies to the automatic `UNSURE` → category sweep triggered by a manual correction. Already-categorized transactions are still never touched.

B) Broaden it — when you correct a transaction, also let you optionally find and review other transactions that already have *some* category assigned (not just `UNSURE`) but match the corrected one, so you can bulk-apply the same correction to them too.

C) Both — keep the existing `UNSURE` sweep (now gated by review), plus add a separate, explicitly-triggered "find similar already-categorized transactions" action you can run on demand.

X) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 2: When should the change actually take effect, relative to your review?

A) Propose-first — nothing is written to any other transaction until you approve it in the panel. This changes today's behavior from automatic to gated.

B) Apply-then-review — keep today's immediate auto-apply behavior exactly as-is, but log every automatic change into a review list you can inspect afterward, with the ability to revert individual rows back to their prior category.

C) Hybrid — auto-apply immediately only when the match confidence is very high; route borderline/lower-confidence matches to the review panel instead of applying them.

X) Other (please describe after [Answer]: tag below)

[Answer]:C

## Question 3: Where should this review panel live in the app?

A) A new page of its own, with its own nav link.

B) A new section/tab inside the existing Ingestion page (it already shows run history in a similar list format).

C) A new section/tab inside Settings.

X) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 4: Selection and bulk actions

You mentioned being able to select one, several, or all of the proposed transactions. Confirming the exact behavior:

A) Per-row approve/reject checkboxes, plus a "select all" control and bulk "approve selected" / "reject selected" buttons.

B) Per-row approve/reject only — no bulk selection or bulk actions.

X) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 5: What happens to a transaction whose proposed change you reject (or never review)?

A) It's left exactly as-is (e.g. still `UNSURE`), and the proposal is simply discarded — the same category could be proposed again on a future correction.

B) It's left exactly as-is, but the system remembers the rejection so that specific category is not proposed again for that transaction.

X) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 6: Should pending reviews be surfaced anywhere else in the app (e.g. a count/badge in navigation), or is visiting the panel manually enough?

A) Yes — show a count/badge somewhere prominent so a pending review doesn't get forgotten.

B) No — a manual visit to the panel is enough, no ambient indicator needed.

X) Other (please describe after [Answer]: tag below)

[Answer]:A
