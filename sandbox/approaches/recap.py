#!/usr/bin/env python3
"""Sandbox approaches for /recap — 24h signal recap.

Axes: baseline (production prompt) · code-first cited timeline (model picks
message numbers, code owns times/actors) · free-text narrative · threads
(same signals grouped by topic instead of chronology).
"""

import core
from formatter import fmt_recap

WINDOW = "24h"
MAX_MSGS = 400

KINDS = ["decision", "ask", "commitment", "blocker", "data", "update"]

# ── asis: the exact production prompt/schema/render ──────────────────────────


def build_asis(ctx):
    context = core.formatted_window(ctx, WINDOW)
    prompt = f"""You are a sharp executive assistant. Produce a chronological 24-hour timeline of key events from this WhatsApp chat. Filter out trivial chatter, generic acknowledgments ("ok", "done", "will do"), and system messages. Only include significant signals: decisions, escalations, commitments, blocks, and data shared. Keep the action summaries concise but highly informative. 

Chat History (last 24h, timestamps in IST):
{context}

Return ONLY valid JSON with:
- "date_str": string (e.g., "14 Apr 2026")
- "events": array of objects in chronological order, each with:
    "time": string (e.g., "3:49 PM"),
    "actor": string (sender name),
    "action": string (what important thing they said/did)
- "summary": string (1-2 line summary at the end)

Output ONLY valid JSON, no markdown.
"""
    fallback = {"events": [], "summary": "Analysis failed.", "date_str": ""}
    schema = {
        "type": "object",
        "properties": {
            "date_str": {"type": "string"},
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "time": {"type": "string"},
                        "actor": {"type": "string"},
                        "action": {"type": "string"},
                    },
                    "required": ["time", "actor", "action"],
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["events", "summary"],
    }
    return prompt, schema, fallback


# ── narrative: free text morning brief ───────────────────────────────────────


def build_narrative(ctx):
    context = core.formatted_window(ctx, WINDOW)
    return f"""You are a sharp executive assistant. Write the 24-hour recap for this WhatsApp group — the owner reads it on his phone.

Chat History (last 24h, timestamps in IST):
{context}

Write a tight morning-brief in plain WhatsApp text (bold *like this*, italics _like this_):
1. One line: how busy the day was and the dominant thread.
2. The key events, each one line, most important first — decisions, asks, commitments, blocks, data shared. Name the actor.
3. Last line: what needs attention next.

Rules: skip trivial chatter and acks ("ok", "done", "will do"); never invent facts or times; no markdown headers; no preamble; under 1200 characters.
"""


# ── cited: code-first timeline (model picks msgs, code renders time/actor) ───

CITED_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "msg": {"type": "integer"},
                    "action": {"type": "string"},
                    "kind": {"type": "string", "enum": KINDS},
                },
                "required": ["msg", "action", "kind"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["events", "summary"],
}

THREADS_SCHEMA = {
    "type": "object",
    "properties": {
        "threads": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "msg": {"type": "integer"},
                                "action": {"type": "string"},
                            },
                            "required": ["msg", "action"],
                        },
                    },
                },
                "required": ["title", "events"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["threads", "summary"],
}

_CITED_PROMPT = """You are the signal filter for a manager's 24-hour WhatsApp recap. Read the numbered messages below (times IST; today is {today}). Pick ONLY significant signals: decisions, asks, commitments, blockers, data shared. Skip chatter and acks ("ok", "done", "will do").

Messages:
{transcript}

Return ONLY JSON:
- "events": chronological, each {{"msg": message number, "action": one line — what happened, at most 20 words, "kind": {kinds}}}.
- "summary": 1-2 lines on the day, naming the dominant thread.
Rules: never write times or dates yourself — the message number carries them; merge duplicate/noise; at most 12 events.
"""


def _pick(index, data, key="events"):
    """Validate + dedupe cited msgs; newest-last chronological order."""
    picked = []
    seen = set()
    for ev in (data or {}).get(key) or []:
        try:
            n = int(ev.get("msg"))
        except (TypeError, ValueError):
            continue
        if n in index and n not in seen:
            seen.add(n)
            picked.append((n, ev))
    picked.sort(key=lambda pair: index[pair[0]][0])
    return picked


def run_cited(ctx, call_json):
    import ledger

    index, transcript, _people = core.numbered_window(ctx, WINDOW, MAX_MSGS)
    now = ledger._now(ctx)
    prompt = _CITED_PROMPT.format(today=f"{now:%a %d %b %Y}", transcript=transcript,
                                  kinds="|".join(KINDS))
    data, _err = call_json(prompt, CITED_SCHEMA, {"events": [], "summary": ""})
    return render_cited(data, index, now)


def render_cited(data, index, now) -> str:
    if not isinstance(data, dict):
        return "📌 *24h Recap*\n\n_Analysis failed._"
    picked = _pick(index, data)
    if not picked:
        return "📌 *24h Recap*\n\n_No significant events in the last 24 hours._"
    day = index[picked[-1][0]][0]
    lines = [f"📋 *Last 24 Hrs* — {day:%a %d %b}", ""]
    for n, ev in picked:
        dt, actor, _text = index[n]
        action = (ev.get("action") or "").strip()
        lines.append(f"🕒 {dt:%H:%M} · *{actor}* — {action}")
    summary = (data.get("summary") or "").strip()
    if summary:
        lines += ["", f"🔍 *Summary:* {summary}"]
    return "\n".join(lines)


def run_threads(ctx, call_json):
    import ledger

    index, transcript, _people = core.numbered_window(ctx, WINDOW, MAX_MSGS)
    now = ledger._now(ctx)
    prompt = f"""You are the signal filter for a manager's 24-hour WhatsApp recap. Read the numbered messages below (times IST; today is {now:%a %d %b %Y}) and group the significant signals by thread. Skip chatter and acks.

Messages:
{transcript}

Return ONLY JSON:
- "threads": 2-5 threads; each {{"title": short topic name, "events": [{{"msg": message number, "action": one line — what happened, at most 20 words}}]}}.
- "summary": 1-2 lines on the day.
Rules: every event must cite a message number; never write times or dates yourself; merge duplicates; at most 12 events total.
"""
    data, _err = call_json(prompt, THREADS_SCHEMA, {"threads": [], "summary": ""})
    return render_threads(data, index, now)


def render_threads(data, index, now) -> str:
    if not isinstance(data, dict):
        return "📌 *24h Recap*\n\n_Analysis failed._"
    threads = []
    for t in data.get("threads") or []:
        picked = _pick(index, t)
        if picked:
            threads.append((t.get("title") or "Thread", picked))
    if not threads:
        return "📌 *24h Recap*\n\n_No significant events in the last 24 hours._"
    threads.sort(key=lambda pair: max(index[n][0] for n, _ev in pair[1]), reverse=True)
    last_dt = max(index[n][0] for _t, picked in threads for n, _ev in picked)
    lines = [f"📋 *Last 24 Hrs* — {last_dt:%a %d %b}",
             f"_{len(threads)} threads · {sum(len(p) for _t, p in threads)} signals_", ""]
    for i, (title, picked) in enumerate(threads, 1):
        lines.append(f"*{i}. {title}*")
        for n, ev in picked:
            dt, actor, _text = index[n]
            lines.append(f"• {dt:%H:%M} *{actor}* — {(ev.get('action') or '').strip()}")
        lines.append("")
    summary = (data.get("summary") or "").strip()
    if summary:
        lines += [f"🔍 *Summary:* {summary}"]
    return "\n".join(lines).strip()


# ── registry ─────────────────────────────────────────────────────────────────

APPROACHES = [
    {
        "name": "asis",
        "title": "Production as-is",
        "desc": "the exact prompt/schema/render shipping in wacmd.py today",
        "hypothesis": "baseline; model writes the times itself → risk of wrong times",
        "llm": True, "window": WINDOW,
        "build": build_asis, "render": fmt_recap,
        "stats": lambda d: {"events": len((d or {}).get("events") or [])},
    },
    {
        "name": "cited",
        "title": "Cited timeline (code-first)",
        "desc": "numbered transcript; model picks msg numbers, code renders exact IST time + actor",
        "hypothesis": "no invented times or actors; strict signal filter; best precision",
        "llm": True, "window": WINDOW,
        "custom_run": run_cited,
        "stats": lambda d: {},
    },
    {
        "name": "narrative",
        "title": "Morning brief (free text)",
        "desc": "no schema: day pulse, key events most-important-first, what needs attention",
        "hypothesis": "most readable; no guardrails, risks invented detail",
        "llm": True, "window": WINDOW,
        "build": build_narrative,
        "render": lambda t: t.strip(),
        "stats": lambda d: {},
    },
    {
        "name": "threads",
        "title": "Threads view (code-first)",
        "desc": "same cited signals, grouped by topic, threads ordered by latest activity",
        "hypothesis": "easier to scan when the chat interleaves several threads",
        "llm": True, "window": WINDOW,
        "custom_run": run_threads,
        "stats": lambda d: {},
    },
]

BY_NAME = {a["name"]: a for a in APPROACHES}
