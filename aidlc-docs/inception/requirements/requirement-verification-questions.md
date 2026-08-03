# Requirements Clarification Questions — Bank Transaction Insights App

Please answer each question by filling in the letter choice after the `[Answer]:` tag. If none of the options match, choose the last option (Other) and describe your preference. Let me know when you're done.

## Question 1 — Category Whitelist
You mentioned you'll provide the category whitelist in a follow-up message. Should I wait for that list before finalizing requirements, or proceed now with a placeholder set you can edit later?

A) Wait — I will provide the full category list before requirements are finalized

B) Proceed with a reasonable placeholder list now (e.g. Groceries, Dining, Transport, Utilities, Rent/Mortgage, Salary/Income, Entertainment, Healthcare, Shopping, Transfers, Fees/Charges, UNSURE) — I will edit it later

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 2 — Google OAuth Account Type
Whose Google identity should the app authenticate as when reading the Drive folder?

A) My personal Google account — I will sign in interactively via OAuth (Authorization Code flow) the first time, and the app stores a refresh token for subsequent manual-trigger runs

B) A Google Cloud "service account" that has been granted access to the shared folder (no interactive login; requires me to share the folder with the service account's email)

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 3 — PDF Statement Format
Are all bank statements digitally generated PDFs with selectable text, or might some be scanned/image-based (requiring OCR)?

A) All are digital/text-based PDFs (no OCR needed)

B) Some may be scanned images and will require OCR

C) Not sure — build in OCR fallback to be safe

X) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 4 — Number of Banks / Statement Layouts
How many distinct banks / statement layouts should the app support parsing out of the box?

A) Just 1–2 known banks/layouts (I can tell you which, and we hard-code parsers for them)

B) Several known banks (3–6), each with a distinct fixed layout

C) Unknown/variable — the app should use a generic/LLM-assisted extraction approach that can adapt to new layouts without custom code per bank

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 5 — Transaction Categorization Method
You want categorization to use similar past transactions as precedence. How should this matching/decision logic work technically?

A) Use an LLM (e.g., Claude API) to classify each transaction, given the whitelist and examples of similarly-worded past transactions pulled from the database as context

B) Use a local rule/keyword-matching engine plus fuzzy text-similarity search against past categorized transactions (no external LLM calls, fully offline)

C) Hybrid: fuzzy similarity match against past transactions first; fall back to an LLM only when no sufficiently similar past transaction exists

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 6 — Manual Re-categorization
Should users be able to manually change a transaction's category after import, and should that manual correction be used as future precedent for similar transactions?

A) Yes to both — manual edits are allowed and are prioritized as learning examples for future auto-categorization

B) Yes, allow manual edits, but do not feed them back into auto-categorization logic

C) No manual editing needed

X) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 7 — Duplicate Statement Detection
How should the app determine a statement PDF has "already been processed" to avoid reprocessing?

A) Track by Google Drive file ID + file modified-timestamp/checksum (skip if unchanged since last run)

B) Track by filename only

C) Track by content hash of the extracted text (catches renamed-but-identical files)

X) Other (please describe after [Answer]: tag below)

[Answer]:C

## Question 8 — Web App Authentication
Is this a single-user personal app, or does it need multi-user login/access control?

A) Single user — no login needed for the web app itself (only Google OAuth for Drive access), runs locally on my machine

B) Single user, but still wants a simple login/password to protect the web UI

C) Multi-user with accounts and per-user data isolation

X) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 9 — Currency Handling
Do your bank statements involve multiple currencies, or a single currency?

A) Single currency throughout

B) Multiple currencies — store currency per transaction and handle conversion/display accordingly

X) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 10 — Dashboard Insights Priorities
Which financial insights matter most for the dashboards? (select all that feel essential — pick the closest single option, we can refine later)

A) Spending by category over time (trends, monthly breakdowns)

B) Income vs. expenses / net cash flow over time

C) Bank/account-level breakdowns and balances

D) All of the above (comprehensive dashboard covering category trends, cash flow, and per-bank views)

X) Other (please describe after [Answer]: tag below)

[Answer]:D

## Question 11 — Tech Stack Preference
Do you have a preferred technology stack, or should the AI choose based on best fit?

A) Let the AI choose the best-fit modern stack (e.g., React frontend, Python/FastAPI backend, PostgreSQL)

B) I have specific preferences (describe below)

X) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 12 — Deployment Scope
Is this strictly for local/personal use via `docker-compose up`, or should it be designed for eventual cloud deployment too?

A) Strictly local personal use via docker-compose — no cloud deployment concerns

B) Local now, but design with future cloud deployment in mind (e.g., externalized config, environment-based secrets)

X) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 13 — Security Extension
Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for production-grade applications)

B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental projects)

X) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 14 — Property-Based Testing Extension
Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints (recommended for projects with business logic, data transformations, serialization, or stateful components)

B) Partial — enforce PBT rules only for pure functions and serialization round-trips (suitable for projects with limited algorithmic complexity)

C) No — skip all PBT rules (suitable for simple CRUD applications, UI-only projects, or thin integration layers with no significant business logic)

X) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 15 — Resiliency Baseline Extension
Should the resiliency baseline be applied to this project? (This applies AWS Well-Architected-derived, design-time best practices for fault tolerance/observability — not a certification.)

A) Yes — apply the resiliency baseline as directional best practices and design-time guidance

B) No — skip the resiliency baseline (suitable for PoCs, prototypes, and personal-use projects where rapid iteration matters more than reliability)

X) Other (please describe after [Answer]: tag below)

[Answer]:B
