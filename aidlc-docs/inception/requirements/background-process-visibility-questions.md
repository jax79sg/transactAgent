# Background Process Visibility — Clarifying Questions

Please answer each question by filling in the letter choice after the `[Answer]:` tag. If none of the options match, choose the last option (Other) and describe your preference.

Context pulled from the live system before writing these:
- The Ingestion Worker processes exactly one background job at a time per 5-second poll cycle, checked in this priority order: **ingestion run → recategorization job → backup run → recurring-payment detection scan → embedding batch**.
- Only the first two (**ingestion run**, **recategorization job** — your own example) have a real `queued`/`running` status in the database today. The other three (backup run, detection scan, embedding batch) are recorded **only after they finish** — there's currently no database row, and therefore no way to query, "is this happening right now" for those three, without adding a real in-progress status to track (a schema change, not just new UI).
- The app already has a working "is the worker busy right now" check (built for the Settings page's restart guidance) — but it only covers the first two job types for the reason above.
- Today's nav bar already shows two badges (pending-review count, recurring-payments attention count) — both are **backlog counts** ("N things await your review"), not activity indicators. There's currently no way to tell "a recategorization scan is running right now" as distinct from "N proposals are waiting for you."

## Question 1
Which background job types should this feature cover?

A) Just the two that already have real in-progress tracking today: ingestion runs and recategorization jobs (your own example) — no schema changes needed, can ship faster

B) All five job types, including backup runs, detection scans, and embedding batches — requires adding a real in-progress status to those three (a database migration + worker logic change, not just UI)

C) The two from (A) now, with the other three planned as a later follow-up once this first version is proven useful

D) Other (please describe after [Answer]: tag below)

[Answer]:C 

## Question 2
Where should this indicator live?

A) In the nav bar, always visible on every page (similar placement to the existing pending-review/recurring-payments badges) — you'd see it no matter what page you're on

B) A dedicated small panel/widget on one page (e.g. the Dashboard or Review page) — only visible when you're on that page

C) Both — a small persistent nav bar indicator, plus more detail available on a dedicated page/panel if you click into it

D) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 3
What should it actually show?

A) A simple on/off signal — "something is running" vs. "idle" — no detail about which job type

B) Which specific job type is currently running (e.g. "Recategorization scan running…", "Ingestion in progress…") — one at a time, since the worker only ever does one thing at once

C) Same as (B), plus a short log/history of recently-completed background activity (e.g. "Backup completed 2 minutes ago", "Detection scan completed at 3:00am") — most useful for the write-once job types from Question 1, where "after the fact" is the only visibility that exists

D) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 4
How quickly should it reflect reality? (Existing polling in this app ranges from 3s for the active Ingestion page down to 5min for the recurring-payments nav badge — faster polling means more API calls, but a more "live" feel)

A) Fast — a few seconds, so it feels close to real-time (matches how the Ingestion page's own progress view already behaves)

B) Moderate — matching the existing pending-review nav badge's 30-second polling

C) Doesn't need to be fast — this is a "did something run recently" indicator, not a live progress bar; a minute or more between refreshes is fine

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 5
Visual style — should it match the existing nav bar badge look (a small amber pill with a count, like the two that already exist), or something visually distinct (e.g. a spinner/pulsing dot, since this is about *activity* rather than a *count*)?

A) Reuse the existing amber-pill badge style, for visual consistency with the two badges already there

B) Something visually distinct from a count-badge (e.g. a spinner or pulsing indicator) — since "3 things happened" and "something is happening right now" are different kinds of information and arguably shouldn't look the same

C) No strong preference — your call on what reads clearly

D) Other (please describe after [Answer]: tag below)

[Answer]: B
