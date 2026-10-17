# Contributing

Small project: Go bridge (`bridge/`), Python command engine (`wacmd.py`, `engine.py`,
`ledger.py`, `mechat.py`), offline tests (`tests/`).

```bash
pip install -r requirements.txt
python3 -m pytest tests/ -q      # no network, no keys needed
(cd bridge && go build ./...)    # bridge must compile
```

## Sandbox — the `/pending` approach lab

Before a change to `/pending` reaches production, prove it on real history. Dump a chat's
window to JSON and replay any approach offline:

```bash
python3 sandbox/dump_context.py --chat "Your Group"    # writes sandbox/data/
python3 sandbox/run.py --approach ledger --pulse        # ledger | digest6 | chrono | twopass
```

- `--pulse` runs an ask-recall guard sweep over the transcript every N messages.
- The `ledger` approach (open loops by owner) is what production `/pending` runs.
- Outputs land in `sandbox/outputs/`.

## Model benchmarking

Compare Gemini models on *your real history* before changing the default
(`GEMINI_MODEL` in `engine.py`):

```bash
python3 scripts/evaluate_models.py
```

It picks your most active group, runs simulated commands per model and grades with a
judge prompt (output quality, hallucinations, context retention).

## Diagnostics

```bash
python3 scripts/test_api.py      # Gemini key health (text + strict-JSON generation)
python3 scripts/test_local.py    # full command dry-run against a seeded mock DB
python3 scripts/gemini_check.py  # prints: valid | invalid | missing (used by the setup page)
bash scripts/clean.sh            # reset local stores/logs
```

## Ship checklist

1. `python3 -m pytest tests/ -q` green.
2. Bridge compiles.
3. Real-device smoke test: `/pending`, `/sotu`, `/stats`, `/recap`, `/eli5 <topic>` in a
   live group — answers land in the Me chat, nothing is written to the source chat.
4. Update `CHANGELOG.md`.
