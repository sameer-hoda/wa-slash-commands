#!/usr/bin/env python3
"""Approach registry for the /pending sandbox.

Each approach knows how to build its prompt(s), how to render the raw model
result into a WhatsApp message, and what to count. ``run.py`` executes them
and compares.
"""

import datetime
import json

import engine
from formatter import fmt_pending
from ledger import LEDGER_ENTRY, is_bot_noise


def formatted_window(ctx: dict, window: str) -> str:
    w = ctx["windows"][window]
    msgs = []
    for m in w["messages"]:
        ts = datetime.datetime.fromisoformat(m["ts"]) if m.get("ts") else None
        msgs.append((m["sender"], m["content"], ts))
    if ctx.get("options", {}).get("clean"):
        msgs = [m for m in msgs if not is_bot_noise(m[1])]
    return engine.format_messages_ist(msgs)


def initiative_stats(data) -> dict:
    if not isinstance(data, dict):
        return {}
    inits = data.get("initiatives") or []
    sizes = [len(i.get("updates") or []) for i in inits]
    return {
        "inits": len(inits),
        "upd_max": max(sizes) if sizes else 0,
        "upd_total": sum(sizes),
        "next": sum(1 for i in inits if (i.get("next_steps") or "").strip()),
    }


# ── shared prompts / schemas ──────────────────────────────────────────────────

MERGE_SCHEMA = {
    "type": "object",
    "properties": {
        "initiatives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "updates": {"type": "array", "items": {"type": "string"}},
                    "next_steps": {"type": "string"},
                },
                "required": ["title", "updates", "next_steps"],
            },
        }
    },
    "required": ["initiatives"],
}
MERGE_FALLBACK = {"initiatives": []}

MERGE_RULES = """Rules:
- At most 6 initiatives, ordered by urgency. Prefer fewer, stronger initiatives.
- Up to 4 updates per initiative, each ONE line: "<date> — outcome in one clause".
- Merge related micro-messages into a single update — one line per outcome, not per message.
- Never quote raw chat verbatim; never invent dates, names, or numbers.
- next_steps: exactly one line, "Who does what next".
- Ignore banter, opinions, and bot/system messages.

Return ONLY valid JSON: {"initiatives": [{"title", "updates": [...], "next_steps"}]}
"""


# ── approaches ────────────────────────────────────────────────────────────────

DIGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "initiatives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "status": {"type": "string"},
                    "next_steps": {"type": "string"},
                },
                "required": ["title", "status", "next_steps"],
            },
        },
    },
    "required": ["headline", "initiatives"],
}


def build_digest6(ctx):
    context = formatted_window(ctx, "30d")
    prompt = f"""You are a sharp executive chief of staff. Produce a one-screen pulse of open work in this chat.

Chat History:
{context}

Rules:
- headline: ONE line summarizing the chat's current pulse.
- At most 6 initiatives, urgency order. Prefer fewer, stronger ones.
- status: ONE clause on where it stands now, with its latest date.
- next_steps: ONE line, "Who does what next".
- Merge aggressively; ignore banter and bot/system messages; never invent facts.

Return ONLY valid JSON: {{"headline": "...", "initiatives": [{{"title", "status", "next_steps"}}]}}
"""
    return prompt, DIGEST_SCHEMA, {"headline": "", "initiatives": []}


def render_digest(data) -> str:
    if not isinstance(data, dict) or not data.get("initiatives"):
        return "✅ *No open work found.*"
    lines = []
    headline = (data.get("headline") or "").strip()
    if headline:
        lines.append(f"📮 {headline}")
        lines.append("")
    for i, init in enumerate(data["initiatives"], 1):
        lines.append(f"*{i}. {init.get('title', 'Untitled')}*")
        status = (init.get("status") or "").strip()
        if status:
            lines.append(f"• {status}")
        nxt = (init.get("next_steps") or "").strip()
        if nxt:
            lines.append(f"⏭ {nxt}")
        lines.append("")
    return "\n".join(lines).strip()


def build_chrono(ctx):
    context = formatted_window(ctx, "30d")
    return f"""You are a sharp executive chief of staff. Write a WhatsApp-formatted digest of open work in this chat.

Chat History:
{context}

Rules:
- Group by workstream, at most 6, urgency order. One block per workstream.
- Each block, exactly two lines:
  *Name* — latest state (with date)
  ⏭ Next: who does what
- Weight the last 7 days; drop anything resolved; ignore banter and bot outputs.
- Plain WhatsApp text (bold with *asterisks*). No headers, no markdown, no preamble.
"""


FULL_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "actor": {"type": "string"},
                    "what": {"type": "string"},
                    "kind": {"type": "string",
                             "enum": ["ask", "promise", "blocker", "decision", "update"]},
                    "topic": {"type": "string"},
                },
                "required": ["date", "actor", "what", "kind", "topic"],
            },
        }
    },
    "required": ["events"],
}


def run_twopass(ctx, call_json) -> str:
    context = formatted_window(ctx, "30d")
    p1 = f"""Extract the signal events from this chat as a structured list.
One event per distinct action, decision, request, promise, or blocker. Deduplicate. Do not summarize; do not merge.
Newest last, at most 40.

Chat History:
{context}

Return ONLY valid JSON: {{"events": [{{"date", "actor", "what", "kind", "topic"}}]}}
"""
    events, _u1 = call_json(p1, FULL_SCHEMA, {"events": []})
    p2 = f"""You are a sharp executive chief of staff. Merge these extracted events into the current state of open work for the owner.

Events JSON:
{json.dumps(events, ensure_ascii=False)}

{MERGE_RULES}"""
    merged, _u2 = call_json(p2, MERGE_SCHEMA, MERGE_FALLBACK)
    return fmt_pending(merged)


# ── registry ──────────────────────────────────────────────────────────────────

APPROACHES = [
    {
        "name": "digest6",
        "title": "One-screen pulse (≤6, no update lists)",
        "desc": "headline + ≤6 items with a one-clause status and a next step",
        "hypothesis": "fastest to read; drops history, risks missing nuance",
        "llm": True, "window": "30d",
        "build": build_digest6, "render": render_digest,
        "stats": lambda d: {**initiative_stats(d), "headline": bool((d or {}).get("headline"))},
    },
    {
        "name": "chrono",
        "title": "Chief-of-staff blocks (free text)",
        "desc": "≤6 workstream blocks, two lines each, last-7d weighted",
        "hypothesis": "most human-sounding; no schema guardrails",
        "llm": True, "window": "30d",
        "build": build_chrono, "render": lambda t: t.strip(),
        "stats": lambda d: {},
    },
    {
        "name": "twopass",
        "title": "Extract → merge (2 LLM passes)",
        "desc": "pass 1 extracts raw events, pass 2 merges them into initiatives",
        "hypothesis": "best precision when many people talk over each other",
        "llm": True, "window": "30d",
        "custom_run": run_twopass,
        "stats": lambda d: {},
    },
]

APPROACHES.append(LEDGER_ENTRY)

BY_NAME = {a["name"]: a for a in APPROACHES}
