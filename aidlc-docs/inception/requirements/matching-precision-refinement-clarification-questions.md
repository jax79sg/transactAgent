# Matching Precision Refinement — Clarification Questions

Your answers to the first question file resolved most ambiguity, but combining a few answers surfaced 2 follow-up points that change the actual design, so asking before drafting requirements.md.

## Clarification 1: What exactly counts as "disagreement"?

Q1=A means the LLM classifies **every** transaction. Q2=C means when the LLM and similarity-matching disagree, the transaction becomes UNSURE with both candidates offered for the human to pick. But there are two sub-cases Q2 didn't cover:

- Similarity finds a match, but the LLM abstains (its own constrained-whitelist call returns literal `UNSURE`) — is that a "disagreement," or does the confident signal (similarity) just win since there's nothing to disagree with?
- The LLM finds a category, but similarity finds no match at all (today's fallback case) — same question: does the LLM's answer just win, or does "no similarity match" also count as needing review?

### Question 1
When only ONE of the two signals (similarity match, LLM classification) produces a real category and the other abstains/finds nothing, what should happen?

A) Trust whichever signal is confident and auto-assign its category directly — "disagreement" only applies when BOTH signals produce a category AND those categories differ

B) Treat it the same as a disagreement — route to review with the one available candidate offered, rather than auto-assigning anything the LLM didn't independently confirm (or vice versa)

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Clarification 2: How should "offer both options" actually be surfaced?

The app already has two different places a user resolves an unclear category:
- The plain UNSURE bucket in the Transactions page (click the category cell, pick from a dropdown — no suggestions shown today)
- The dedicated `/review` page (`ReviewPage`/`ProposalTable`, built for Epic 6's `RecategorizationProposal` flow) — designed for exactly this "here are candidate categories, approve/reject/pick" interaction pattern

### Question 2
Where should a disagreement (both-candidates) transaction be surfaced for the human to decide?

A) Extend the existing UNSURE flow in the Transactions page — pre-populate the correction dropdown with the two suggested categories as quick-pick buttons (e.g. "Groceries (similarity match)" / "Dining (LLM)"), still just a plain UNSURE-category transaction underneath

B) Route it through the existing `/review` page instead, as a new kind of proposal item (reusing the `ProposalTable`/`ProposalRow` approve-or-pick-one pattern already built for `RecategorizationProposal`) rather than leaving it sitting as a bare UNSURE transaction

C) Other (please describe after [Answer]: tag below)

[Answer]: B
