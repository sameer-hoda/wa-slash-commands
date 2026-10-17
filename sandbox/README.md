# /pending Sandbox

An offline-ish command-line lab to pick the best **prompt + algorithm** for the
`/pending` command before we merge a winner into `wacmd.py`.

The data dump is read-only and private (`sandbox/data/` and `sandbox/outputs/`
are gitignored). LLM approaches call Gemini with the key from the repo `.env`.

## Quickstart

```bash
cd wa-slash-commands

python3 sandbox/dump_context.py --chat "branding OKR"   # snapshot the chat once
python3 sandbox/run.py --list                           # see the approaches
python3 sandbox/run.py --all --clean                    # full dice-off
```

Tips:

```bash
python3 sandbox/run.py --approach ledger --repeat 3     # variance check
python3 sandbox/run.py --approach ledger --temp 0.1     # temperature sweep
python3 sandbox/run.py --approach ledger --model gemini-3.5-flash-lite
python3 sandbox/run.py --approach ledger --pulse        # live pulses + answer in Me chat
python3 sandbox/run.py --all --save                     # drop outputs/ for review
```

## The approaches

| # | name | what it is |
|---|---|---|
| 1 | `digest6` | one-screen pulse: headline + ≤6 items (one-clause status + next) |
| 2 | `chrono` | free-text chief-of-staff blocks, last-7d weighted (no schema) |
| 3 | `twopass` | pass 1 extracts raw events → pass 2 merges into initiatives |
| 4 | `ledger` | open-loops ledger: cited asks grouped by owner — code owns all dates |

`ledger` preprocesses in code (IST labels, numbered messages, @mention → name via
the engine's contact lookup, bot noise dropped), the LLM only classifies and cites
message numbers, and code validates every citation, computes ages and renders.

> **`ledger.py` now lives at the repo root** — the same engine ships in the
> production `/pending` (two samples unioned, names normalized, dates in code).

`--clean` drops bot noise (`/commands` and old digests like `🎯 … ⏭ *Next:*`)
from the 30d context windows (ledger always cleans its own transcript).

## How to judge

Read the boxed output for each approach, then the comparison table:
**chars** (green < 1500), **inits**, **upd≤**, **next**, tokens, time.
Better: score against a small golden set of loops you know are true —
recall and wrong-items matter more than character count.

## After you pick

Tell me the winner (e.g. "ledger with flash, temp 0.1") and I port it
into `wacmd.py` (prompt/schema/format), update the golden tests, and it ships with
the next `/pending`.
