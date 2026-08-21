# Recategorization Scope Narrowing — Clarifying Questions

Please answer each question by filling in the letter choice after the `[Answer]:` tag. If none of the options match, choose the last option (Other) and describe your preference.

Context confirmed by reading the live code before writing these:
- The retroactive recategorization scan (`recategorize_unsure_from_precedent`, `ingestion-worker/src/ingestion_worker/categorization/service.py`) currently scans **two** candidate buckets whenever you manually correct a transaction's category: (A) all `UNSURE` transactions, and (B) **every other transaction in the database**, regardless of how it got its current category (manual, similarity-matched, or LLM-assigned) — this is the noisy, low-accuracy bucket you're asking to remove.
- "Others" is a real, plain, user-editable category in your whitelist (`database/src/transactagent_db/seed_categories.py`) — not a special/reserved category like `UNSURE` is. It has no distinguishing flag; it's identified only by its name, the same as "Bills" or "Groceries" would be, and you could rename or delete it via Settings like any other category.
- Bucket B matches are never auto-applied today (an existing safeguard, WR-10) — they always create a `PENDING` proposal for you to approve or reject on the Review page. Bucket A (`UNSURE`) matches *can* auto-apply if the similarity score is high enough.

## Question 1
"Others" isn't a reserved category — it's just a name in your editable whitelist. How should the system identify it for this new, narrower bucket?

A) Match by exact name "Others" (case-sensitive) — simplest, but breaks silently if you ever rename or delete that category

B) Match by name case-insensitively ("Others", "others", "OTHERS" all count) — slightly more forgiving of typos/case, still breaks if renamed

C) Don't hardcode a name at all — expose it as a configurable setting (like the existing Application Settings feature) so you can point it at whatever category name you actually use, and change it later without a code change

D) Other (please describe after [Answer]: tag below)

[Answer]: D. Don't use others. Just UNSURE will do. 

## Question 2
Should matches found in the new "Others" bucket keep the same conservative behavior Bucket B has today — always a `PENDING` proposal for you to review, never auto-applied — or should "Others" be treated more like the `UNSURE` bucket (eligible to auto-apply above the high-confidence threshold)?

A) Always `PENDING`, never auto-applied — matches today's Bucket B safeguard exactly, most conservative given the accuracy concern that prompted this change

B) Treat it like `UNSURE` — eligible to auto-apply above the existing high-confidence threshold, same as `UNSURE` matches are today

C) Other (please describe after [Answer]: tag below)

[Answer]: C. Don't use Others. See Q1.

## Question 3
Right now there may already be `PENDING` proposals sitting on your Review page that came from the old, broader Bucket B (i.e., proposals for transactions that are neither `UNSURE` nor currently in "Others"). What should happen to those existing proposals once this change ships?

A) Leave them exactly as-is — you'll individually approve or reject them yourself on the Review page, same as any other pending proposal; the new narrower scope only affects *future* recategorization scans

B) Automatically reject/clear them as part of this change, since they no longer match the new intended scope

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 4
Just to confirm the boundary of this change — it should affect only the **retroactive recategorization re-scan** (the one triggered when you manually correct a transaction, which proposes the same fix to similar transactions). It should **not** touch the separate, unrelated logic that auto-categorizes brand-new incoming transactions during ingestion (which already uses a different combination of embedding + LLM + similarity matching). Is that the right scope?

A) Yes — only the retroactive recategorization re-scan changes; new-transaction ingestion-time categorization is untouched

B) No — I also want the new-transaction ingestion-time categorization logic changed (please describe what, after [Answer]: tag below)

[Answer]: A
