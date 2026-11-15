# Claude Code usage of this project

Collected by `scripts/claude_usage.py` from Claude Code's own transcripts into `ledger.json`. Days are UTC. Data through **2026-10-26**.

| | |
|---|---|
| Estimated cost at API list prices | **$878.20** (a floor, see below) |
| API requests | 6,787 in 11 sessions, 2026-08-15 to 2026-10-26 |

## Where the cost goes

| Tokens | Count | Est. cost | Share |
|---|---:|---:|---:|
| Cache reads (the conversation so far, re-read every turn) | 3,097,639,185 | $619.53 | 71% |
| Cache writes (new context stored) | 49,375,417 | $195.89 | 22% |
| Output (of which thinking 2,389,958) | 6,268,153 | $62.68 | 7% |
| Fresh input | 50,609 | $0.10 | 0% |

## By model

| Model | Requests | Output | Cache read | Cache write | Est. cost |
|---|---:|---:|---:|---:|---:|
| `claude-sonnet-5` | 4,743 | 2,929,549 | 2,086,269,224 | 29,260,232 | $562.07 |
| `claude-sonnet-5-5` | 2,044 | 3,338,604 | 1,011,369,961 | 20,115,185 | $316.13 |

## By month

| Month | Sessions | Requests | Output | Est. cost |
|---|---:|---:|---:|---:|
| 2026-08 | 10 | 4,314 | 2,675,199 | $492.86 |
| 2026-09 | 3 | 160 | 104,306 | $21.34 |
| 2026-10 | 1 | 2,313 | 3,488,648 | $363.99 |

## By session

| Session | From | To | Requests | Subagent share | Est. cost |
|---|---|---|---:|---:|---:|
| `85c1d501` | 2026-08-15 | 2026-08-15 | 24 | 0% | $0.60 |
| `bf741e29` | 2026-08-15 | 2026-08-15 | 93 | 82% | $3.16 |
| `5bd88e90` | 2026-08-16 | 2026-08-16 | 438 | 0% | $48.07 |
| `94925555` | 2026-08-16 | 2026-08-16 | 472 | 0% | $53.63 |
| `f1d4992d` | 2026-08-16 | 2026-08-19 | 1,115 | 0% | $135.27 |
| `21741946` | 2026-08-17 | 2026-08-18 | 57 | 0% | $2.84 |
| `4bee1133` | 2026-08-17 | 2026-08-17 | 4 | 0% | $0.15 |
| `af9826a9` | 2026-08-21 | 2026-08-27 | 1,406 | 1% | $182.82 |
| `c9508019` | 2026-08-28 | 2026-09-14 | 624 | 1% | $76.04 |
| `9bdb8fb5` | 2026-08-29 | 2026-09-02 | 221 | 0% | $10.48 |
| `595b9799` | 2026-09-22 | 2026-10-26 | 2,333 | 0% | $365.15 |

## What these numbers are, and are not

- **An estimate of API-equivalent cost, not a bill.** Tokens are priced at Anthropic's list prices (`scripts/claude_usage_prices.json`, as of 2026-10-06), today's prices applied to every date; a subscription plan is billed differently.
- **A floor.** On the one session where Claude Code recorded its own cost, this method came out 2.5% to 9.0% below it: Claude Code also counts calls the transcripts do not record. The prices themselves reproduce Claude Code's figure exactly for the same tokens (checked 2026-10-10).
- **Advisor calls are not counted.** 1,038 requests consulted a stronger advisor model; the transcripts record that it was consulted but not its tokens, so whatever it used is missing.
- **Not complete: nothing before 2026-08-15.** The repository's first commit is on 2026-08-03, but the earliest transcript found is from 2026-08-15; the sessions in between, and any run on another machine, are not in the ledger.
