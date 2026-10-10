# Claude Code usage of this project

Collected by `scripts/claude_usage.py` from Claude Code's own transcripts into `ledger.json`. Days are UTC. Data through **2026-10-10**.

| | |
|---|---|
| Estimated cost at API list prices | **$699.90** (a floor, see below) |
| API requests | 5,521 in 8 sessions, 2026-08-15 to 2026-10-10 |

## Where the cost goes

| Tokens | Count | Est. cost | Share |
|---|---:|---:|---:|
| Cache reads (the conversation so far, re-read every turn) | 2,498,840,701 | $499.77 | 71% |
| Cache writes (new context stored) | 38,280,919 | $151.51 | 22% |
| Output (of which thinking 1,853,526) | 4,853,928 | $48.54 | 7% |
| Fresh input | 41,959 | $0.08 | 0% |

## By model

| Model | Requests | Output | Cache read | Cache write | Est. cost |
|---|---:|---:|---:|---:|---:|
| `claude-sonnet-5` | 3,941 | 2,418,629 | 1,701,340,377 | 23,668,027 | $457.59 |
| `claude-sonnet-5-5` | 1,580 | 2,435,299 | 797,500,324 | 14,612,892 | $242.31 |

## By month

| Month | Sessions | Requests | Output | Est. cost |
|---|---:|---:|---:|---:|
| 2026-08 | 7 | 3,781 | 2,314,323 | $436.25 |
| 2026-09 | 3 | 160 | 104,306 | $21.34 |
| 2026-10 | 1 | 1,580 | 2,435,299 | $242.31 |

## By session

| Session | From | To | Requests | Subagent share | Est. cost |
|---|---|---|---:|---:|---:|
| `85c1d501` | 2026-08-15 | 2026-08-15 | 24 | 0% | $0.60 |
| `bf741e29` | 2026-08-15 | 2026-08-15 | 93 | 82% | $3.16 |
| `5bd88e90` | 2026-08-16 | 2026-08-16 | 438 | 0% | $48.07 |
| `f1d4992d` | 2026-08-16 | 2026-08-19 | 1,115 | 0% | $135.27 |
| `af9826a9` | 2026-08-21 | 2026-08-27 | 1,406 | 1% | $182.82 |
| `c9508019` | 2026-08-28 | 2026-09-14 | 624 | 1% | $76.04 |
| `9bdb8fb5` | 2026-08-29 | 2026-09-02 | 221 | 0% | $10.48 |
| `595b9799` | 2026-09-22 | 2026-10-10 | 1,600 | 0% | $243.47 |

## What these numbers are, and are not

- **An estimate of API-equivalent cost, not a bill.** Tokens are priced at Anthropic's list prices (`scripts/claude_usage_prices.json`, as of 2026-10-06), today's prices applied to every date; a subscription plan is billed differently.
- **A floor.** On the one session where Claude Code recorded its own cost, this method came out 2.5% to 9.0% below it: Claude Code also counts calls the transcripts do not record. The prices themselves reproduce Claude Code's figure exactly for the same tokens (checked 2026-10-10).
- **Advisor calls are not counted.** 574 requests consulted a stronger advisor model; the transcripts record that it was consulted but not its tokens, so whatever it used is missing.
- **Not complete: nothing before 2026-08-15.** The repository's first commit is on 2026-08-03, but the earliest transcript found is from 2026-08-15; the sessions in between, and any run on another machine, are not in the ledger.
