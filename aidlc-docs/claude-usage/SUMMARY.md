# Claude Code usage of this project

Collected by `scripts/claude_usage.py` from Claude Code's own transcripts into `ledger.json`. Days are UTC. Data through **2026-10-18**.

| | |
|---|---|
| Estimated cost at API list prices | **$819.63** (a floor, see below) |
| API requests | 6,411 in 11 sessions, 2026-08-15 to 2026-10-18 |

## Where the cost goes

| Tokens | Count | Est. cost | Share |
|---|---:|---:|---:|
| Cache reads (the conversation so far, re-read every turn) | 2,901,560,913 | $580.31 | 71% |
| Cache writes (new context stored) | 45,154,247 | $179.01 | 22% |
| Output (of which thinking 2,302,989) | 6,021,260 | $60.21 | 7% |
| Fresh input | 49,853 | $0.10 | 0% |

## By model

| Model | Requests | Output | Cache read | Cache write | Est. cost |
|---|---:|---:|---:|---:|---:|
| `claude-sonnet-5` | 4,474 | 2,779,505 | 1,908,406,101 | 26,562,623 | $514.21 |
| `claude-sonnet-5-5` | 1,937 | 3,241,755 | 993,154,812 | 18,591,624 | $305.42 |

## By month

| Month | Sessions | Requests | Output | Est. cost |
|---|---:|---:|---:|---:|
| 2026-08 | 10 | 4,314 | 2,675,199 | $492.86 |
| 2026-09 | 3 | 160 | 104,306 | $21.34 |
| 2026-10 | 1 | 1,937 | 3,241,755 | $305.42 |

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
| `595b9799` | 2026-09-22 | 2026-10-18 | 1,957 | 0% | $306.58 |

## What these numbers are, and are not

- **An estimate of API-equivalent cost, not a bill.** Tokens are priced at Anthropic's list prices (`scripts/claude_usage_prices.json`, as of 2026-10-06), today's prices applied to every date; a subscription plan is billed differently.
- **A floor.** On the one session where Claude Code recorded its own cost, this method came out 2.5% to 9.0% below it: Claude Code also counts calls the transcripts do not record. The prices themselves reproduce Claude Code's figure exactly for the same tokens (checked 2026-10-10).
- **Advisor calls are not counted.** 931 requests consulted a stronger advisor model; the transcripts record that it was consulted but not its tokens, so whatever it used is missing.
- **Not complete: nothing before 2026-08-15.** The repository's first commit is on 2026-08-03, but the earliest transcript found is from 2026-08-15; the sessions in between, and any run on another machine, are not in the ledger.
