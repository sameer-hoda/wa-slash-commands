#!/usr/bin/env python3
"""Approach registry for the Mosaic sandbox lab — one module per command.

Each command module exposes ``APPROACHES``: a list of dicts with the shape
``run.py`` expects:

    name, title, desc, hypothesis, llm, window,
    build → (prompt, schema, fallback) | prompt(text)   + render(data|text)
    — or — custom_run(ctx[, call_json]) + stats(data)

Add a new variant by appending to the command's module; nothing else changes.
"""

from . import eli5, pending, recap, sotu, stats

COMMANDS = {
    "pending": pending.APPROACHES,
    "sotu": sotu.APPROACHES,
    "recap": recap.APPROACHES,
    "stats": stats.APPROACHES,
    "eli5": eli5.APPROACHES,
}


def registry(command: str) -> list:
    if command not in COMMANDS:
        raise SystemExit(f"unknown command {command!r} — pick one of: {', '.join(COMMANDS)}")
    return COMMANDS[command]


def by_name(command: str) -> dict:
    return {a["name"]: a for a in registry(command)}


# backwards compat: bare `import approaches` used to mean /pending
APPROACHES = COMMANDS["pending"]
BY_NAME = by_name("pending")

# backwards compat: the old flat sandbox/approaches.py also exposed these
from ledger import is_bot_noise  # noqa: E402
from .pending import formatted_window, initiative_stats  # noqa: E402,F401
