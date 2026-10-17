#!/usr/bin/env python3
"""Sandbox approaches for /sotu — State of the Union.

Axes: baseline (production prompt) · free-text narrative · code-first cited
themes (code owns dates, model cites message numbers) · two-pass extract→merge.
"""

import json

import core
import engine
from formatter import fmt_sotu

WINDOW = "30d"
MAX_MSGS = 500

# ── asis: the exact production prompt/schema/render ──────────────────────────


def build_asis(ctx):
    context = core.formatted_window(ctx, WINDOW)
    prompt = f"""You are a sharp executive chief of staff. Produce a 'State of the Union' summary for this group chat.

Chat History:
{context}

Return ONLY valid JSON with these exact fields:
- "group_purpose": What this group is about (short paragraph)
- "big_picture_objective": The big picture objective (short paragraph)
- "key_themes": array of objects, each with "title" and "description" (The main discussion themes and their details)
- "recent_happenings": What's been happening recently (last 2 weeks)
- "key_ask": The one thing asked for recently (if any, otherwise omit or say none)

Output ONLY valid JSON, no markdown.
"""
    fallback = {
        "group_purpose": "Analysis unavailable. Please try again.",
        "big_picture_objective": "",
        "key_themes": [],
        "recent_happenings": "",
        "key_ask": "",
    }
    schema = {
        "type": "object",
        "properties": {
            "group_purpose": {"type": "string"},
            "big_picture_objective": {"type": "string"},
            "key_themes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["title", "description"],
                },
            },
            "recent_happenings": {"type": "string"},
            "key_ask": {"type": "string"},
        },
        "required": ["group_purpose", "big_picture_objective", "key_themes",
                     "recent_happenings", "key_ask"],
    }
    return prompt, schema, fallback


# ── narrative: free text, no schema ───────────────────────────────────────────


def build_narrative(ctx):
    context = core.formatted_window(ctx, WINDOW)
    return f"""You are a sharp executive chief of staff. Write the State of the Union for this WhatsApp group — the owner reads it on his phone.

Chat History:
{context}

Write a tight brief in plain WhatsApp text (bold *like this*, italics _like this_):
1. First line: what this group is and the one objective it is chasing right now.
2. "Where we stand" — 3-5 short bullets on the main threads: what moved, what stalled, who is driving. Name brands and people.
3. Last line: the single most important open item right now.

Rules: weight the last two weeks; be specific and concrete; never invent dates; no markdown headers; no preamble; under 1800 characters.
"""


# ── cited: code-first (numbered transcript, cited themes) ────────────────────

CITED_SCHEMA = {
    "type": "object",
    "properties": {
        "group_purpose": {"type": "string"},
        "objective": {"type": "string"},
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "state": {"type": "string"},
                    "msgs": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["title", "state", "msgs"],
            },
        },
        "key_ask": {"type": "string"},
        "ask_msg": {"type": "integer"},
    },
    "required": ["group_purpose", "objective", "themes", "key_ask", "ask_msg"],
}


def run_cited(ctx, call_json):
    import ledger

    index, transcript, people = core.numbered_window(ctx, WINDOW, MAX_MSGS)
    now = ledger._now(ctx)
    prompt = f"""You produce the State of the Union for a manager's WhatsApp group. Read the numbered messages below (times IST; today is {now:%a %d %b %Y}). The numbered transcript is the ONLY source of truth: cite message numbers for every theme; never write dates yourself.

People: {', '.join(people)}

Messages:
{transcript}

Return ONLY JSON:
- "group_purpose": one sentence — what this group is for.
- "objective": one sentence — the single big objective it is chasing.
- "themes": 4-6 current discussion themes, urgency order; each "state" is one clause on where it stands; "msgs" = 2-4 message numbers that best evidence it (most recent first).
- "key_ask": the one thing asked of the owner recently ("" if none); "ask_msg" = its message number (0 if none).
Rules: merge micro-messages; skip banter; never invent facts; "state" describes the CURRENT state.
"""
    data, _err = call_json(prompt, CITED_SCHEMA, {
        "group_purpose": "", "objective": "", "themes": [], "key_ask": "", "ask_msg": 0,
    })
    return render_cited(data, index, now, (ctx.get("meta") or {}).get("chat_name") or "")


def render_cited(data, index, now, chat_name: str = "") -> str:
    import ledger

    if not isinstance(data, dict):
        return "⚠️ *Analysis failed* — nothing usable returned."
    lines = [f"🗳️ *State of the Union — {chat_name}*" if chat_name else "🗳️ *State of the Union*"]
    purpose = (data.get("group_purpose") or "").strip()
    if purpose:
        lines.append(f"_{purpose}_")
    objective = (data.get("objective") or "").strip()
    if objective:
        lines += ["", f"🎯 *The objective* — {objective}"]

    kept = 0
    theme_lines = []
    for t in data.get("themes") or []:
        cites = sorted({int(m) for m in (t.get("msgs") or []) if isinstance(m, (int, float)) and int(m) in index})
        if not cites:
            continue  # uncited theme → drop (model failure, keep it grounded)
        kept += 1
        dt = max(index[n][0] for n in cites)
        label = ledger.day_label(dt, now)
        when = f"{label} {dt:%H:%M}" if label in ("today", "yesterday") else label
        title = (t.get("title") or "Untitled").strip()
        state = (t.get("state") or "").strip()
        theme_lines.append(f"• *{title}* — {state}  _(last: {when} · msgs {', '.join(map(str, cites))})_")
    if theme_lines:
        lines += ["", "*Where it stands*"] + theme_lines

    ask = (data.get("key_ask") or "").strip()
    if ask:
        try:
            ask_n = int(data.get("ask_msg") or 0)
        except (TypeError, ValueError):
            ask_n = 0
        cite = f" _(msg {ask_n})_" if ask_n in index else ""
        lines += ["", f"👉 *The one ask* — {ask}{cite}"]

    if kept == 0 and not purpose and not objective:
        return "⚠️ *Analysis failed* — no cited themes returned."
    return "\n".join(lines).strip()


def cited_stats(data) -> dict:
    if not isinstance(data, dict):
        return {}
    return {"themes": len(data.get("themes") or []),
            "ask": bool((data.get("key_ask") or "").strip())}


# ── twopass: extract events → synthesize SOTU ────────────────────────────────

EVENTS_SCHEMA = {
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

SOTU_SCHEMA = {
    "type": "object",
    "properties": {
        "group_purpose": {"type": "string"},
        "big_picture_objective": {"type": "string"},
        "key_themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["title", "description"],
            },
        },
        "recent_happenings": {"type": "string"},
        "key_ask": {"type": "string"},
    },
    "required": ["group_purpose", "big_picture_objective", "key_themes",
                 "recent_happenings", "key_ask"],
}


def run_twopass(ctx, call_json):
    context = core.formatted_window(ctx, WINDOW)
    p1 = f"""Extract the signal events from this chat as a structured list.
One event per distinct action, decision, request, promise, or blocker. Deduplicate. Do not summarize; do not merge.
Newest last, at most 40.

Chat History:
{context}

Return ONLY valid JSON: {{"events": [{{"date", "actor", "what", "kind", "topic"}}]}}
"""
    events, _u1 = call_json(p1, EVENTS_SCHEMA, {"events": []})
    p2 = f"""You are a sharp executive chief of staff. Using ONLY these extracted events, write the State of the Union for the group.

Events JSON:
{json.dumps(events, ensure_ascii=False)}

Return ONLY valid JSON with these exact fields:
- "group_purpose": What this group is about (short paragraph)
- "big_picture_objective": The big picture objective (short paragraph)
- "key_themes": array of objects, each with "title" and "description"
- "recent_happenings": What's been happening recently (last 2 weeks)
- "key_ask": The one thing asked for recently (if any, otherwise "none")

Never invent facts beyond the events. Output ONLY valid JSON, no markdown.
"""
    data, _u2 = call_json(p2, SOTU_SCHEMA, {
        "group_purpose": "Analysis unavailable.", "big_picture_objective": "",
        "key_themes": [], "recent_happenings": "", "key_ask": "",
    })
    return fmt_sotu(data)


# ── registry ─────────────────────────────────────────────────────────────────

APPROACHES = [
    {
        "name": "asis",
        "title": "Production as-is",
        "desc": "the exact prompt/schema/render shipping in wacmd.py today",
        "hypothesis": "baseline; paragraph-y, may invent dates, all in one call",
        "llm": True, "window": WINDOW,
        "build": build_asis, "render": fmt_sotu,
        "stats": lambda d: {"themes": len((d or {}).get("key_themes") or []),
                            "ask": bool(((d or {}).get("key_ask") or "").strip())},
    },
    {
        "name": "narrative",
        "title": "Chief-of-staff brief (free text)",
        "desc": "no schema: purpose line, where-we-stand bullets, the one open item",
        "hypothesis": "most readable; no guardrails, risks fluff and invented dates",
        "llm": True, "window": WINDOW,
        "build": build_narrative,
        "render": lambda t: t.strip(),
        "stats": lambda d: {},
    },
    {
        "name": "cited",
        "title": "Cited themes (code-first)",
        "desc": "numbered transcript; model cites msg numbers, code computes dates/labels",
        "hypothesis": "grounded and scannable; code owns every date, uncited themes drop",
        "llm": True, "window": WINDOW,
        "custom_run": run_cited,
        "stats": cited_stats,
    },
    {
        "name": "twopass",
        "title": "Extract → synthesize (2 passes)",
        "desc": "pass 1 extracts signal events, pass 2 writes the SOTU from them only",
        "hypothesis": "fewer hallucinations on a 30d window; costs 2 calls",
        "llm": True, "window": WINDOW,
        "custom_run": run_twopass,
        "stats": lambda d: {},
    },
]

BY_NAME = {a["name"]: a for a in APPROACHES}
