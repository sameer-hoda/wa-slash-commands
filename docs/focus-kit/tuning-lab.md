# Focus tuning lab — autonomous rounds (2026-10-26/27)

Time-travel lab: for cutoffs T-24h / T-48h, ran variant prompts against the real
store, then scored with revealed-preference engagement (chats the owner actually
messaged in the 24h AFTER the cutoff). score = 0.6·MRR + 0.4·coverage.
Blinded A/B (variants labeled A/B/C at score time). Prompt-only changes throughout.

## Canonical result

| round | best | score | runner-up |
|---|---|---|---|
| 1 (4 brains) | regret | 0.639 | baseline 0.630 |
| 2 (bugs fixed: due-from-text, fake dues) | regret2 | 0.639 | baseline 0.630 |
| 3 (+diversity protocol, editorial headline) | regret3 | 0.639 | baseline 0.630 |
| 4 (chat_jid required in schema) | baseline3 = regret3 | 0.639 | baseline 0.621 |

Champion shipped to production (`focus.py`): **baseline3 as DEFAULT_RULES** —
tied top score (0.639) with the best diversity (9 distinct chats, max 2 per chat
in round 4) and a built-in COUNT self-check. **regret3** refreshes
`VARIANT_RULES["regret"]` (same score).

Stable finding: regret-family ≥ baseline in all 4 rounds; outcome/voice brains
lose (~0.3); T-48h window does not discriminate (all 0.61 — keep T-24h as the
decisive window).

## Bugs the loop caught (all fixed in production)

1. Fake due dates from timestamps → dues from message TEXT only; due==last_activity nulled.
2. Model omitted chat_jid (baseline3 round 3 scored 0.000) → chat_jid is now a
   REQUIRED (nullable) key in response schema + contract + validator.
3. `@lid` vs `@s.whatsapp.net` spelling splits → `canon_jid` (digits) for
   scoring/linking; no-leakage upper-bound test (`tests/test_focus.py`).
4. Stale `chats.last_message_time` → candidates from `messages`; strict `_parse_ts`.

## Cost

~26 cells × ~$0.001 ≈ $0.03 total. Harness: `focus_tune.py`
(survey/run/rate/score), tests `tests/test_focustune.py`.
Raw cells: `/tmp/focuslab/` (not committed). Human blind ratings (`rate` step)
still open — recommended before any further prompt surgery.
