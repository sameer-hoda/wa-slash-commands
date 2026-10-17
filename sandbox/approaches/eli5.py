#!/usr/bin/env python3
"""Sandbox approaches for /eli5 — explain a topic, grounded in the chat.

Axes: baseline (production free-text prompt) · structured sections rendered by
code · chat-grounded two-pass (model cites the messages it uses).
"""

import core

WINDOW = "30d"
DEFAULT_TOPIC = "webview capping"

# ── asis: the exact production prompt (free text) ────────────────────────────


def _topic(ctx) -> str:
    return (ctx.get("options", {}).get("topic") or "").strip() or DEFAULT_TOPIC


def build_asis(ctx):
    topic_str = _topic(ctx)
    context = core.formatted_window(ctx, WINDOW)
    return f"""Explain the following to a 30-year-old professional. Be concise, clear, and professional.

Topic: "{topic_str}"

Use the chat history below for context if the topic refers to something discussed there.

Chat History:
{context}

Format your response for WhatsApp:
- Start with this exact header: 💡 *ELI30: {topic_str[:60]}*
- Bold key terms with *asterisks*
- Use _italics_ for caveats or nuance
- Keep to 3-4 short paragraphs max
- No ## headers, no --- dividers, no bullet storms
- Write in plain, direct language — no jargon or filler
"""


# ── structured: JSON sections rendered by code ───────────────────────────────

STRUCTURED_SCHEMA = {
    "type": "object",
    "properties": {
        "one_liner": {"type": "string"},
        "analogy": {"type": "string"},
        "points": {"type": "array", "items": {"type": "string"}},
        "why_it_matters": {"type": "string"},
        "caveats": {"type": "string"},
    },
    "required": ["one_liner", "analogy", "points", "why_it_matters", "caveats"],
}


def build_structured(ctx):
    topic_str = _topic(ctx)
    context = core.formatted_window(ctx, WINDOW)
    prompt = f"""Explain the topic below to a smart 30-year-old professional who has never heard it explained properly. Use the chat history for context when the topic is something discussed there.

Topic: "{topic_str}"

Chat History:
{context}

Return ONLY JSON:
- "one_liner": the whole idea in one sentence (max 20 words).
- "analogy": one everyday analogy that makes it click (1-2 sentences).
- "points": 3-5 short points — how it works / what to watch, each one line.
- "why_it_matters": 1-2 sentences — why this group's owner should care.
- "caveats": 1-2 sentences of honest nuance (when it fails / what's debated).
Never invent facts about the chat; keep the tone direct, no filler.
"""
    return prompt, STRUCTURED_SCHEMA, {"one_liner": "", "analogy": "", "points": [],
                                       "why_it_matters": "", "caveats": ""}


def render_structured(data) -> str:
    if not isinstance(data, dict) or not (data.get("one_liner") or data.get("points")):
        return "⚠️ *Analysis failed.*"
    lines = ["💡 *ELI30*", ""]
    if data.get("one_liner"):
        lines += [f"*In one line:* {data['one_liner']}", ""]
    if data.get("analogy"):
        lines += [f"*Think of it like:* {data['analogy']}", ""]
    points = [p for p in data.get("points") or [] if p.strip()]
    if points:
        lines.append("*How it works*")
        lines += [f"• {p.strip()}" for p in points]
        lines.append("")
    if data.get("why_it_matters"):
        lines += [f"*Why it matters:* {data['why_it_matters']}", ""]
    if data.get("caveats"):
        lines.append(f"_{data['caveats']}_")
    return "\n".join(lines).strip()


# ── grounded: two passes — find the chat's messages, then explain with them ──

PICK_SCHEMA = {
    "type": "object",
    "properties": {"msgs": {"type": "array", "items": {"type": "integer"}}},
    "required": ["msgs"],
}

GROUNDED_SCHEMA = {
    "type": "object",
    "properties": {
        "explain": {"type": "string"},
        "from_chat": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "msg": {"type": "integer"},
                    "point": {"type": "string"},
                },
                "required": ["msg", "point"],
            },
        },
        "caveats": {"type": "string"},
    },
    "required": ["explain", "from_chat", "caveats"],
}


def run_grounded(ctx, call_json):
    import ledger

    topic_str = _topic(ctx)
    index, transcript, _people = core.numbered_window(ctx, WINDOW, 400)
    now = ledger._now(ctx)
    p1 = f"""Read the numbered messages (times IST; today is {now:%a %d %b %Y}). Select up to 10 message numbers that discuss "{topic_str}" or give useful context about it. Empty list if nothing is relevant. Do not explain yet.

Messages:
{transcript}

Return ONLY JSON: {{"msgs": [numbers]}}
"""
    picked, _e1 = call_json(p1, PICK_SCHEMA, {"msgs": []})
    nums = sorted({int(n) for n in (picked or {}).get("msgs") or []
                   if isinstance(n, (int, float)) and int(n) in index})
    excerpts = "\n".join(f"[{n}] {index[n][0]:%a %H:%M} · {index[n][1]}: {index[n][2]}"
                         for n in nums) or "(no relevant messages found)"

    p2 = f"""Explain "{topic_str}" to a smart 30-year-old professional, clearly and concisely.

Chat excerpts the group wrote about it:
{excerpts}

Return ONLY JSON:
- "explain": the explanation — 2-3 short paragraphs, plain WhatsApp text (bold *like this*), no headers.
- "from_chat": up to 5 points capturing what THIS group says/decides about it; each {{"msg": cited number, "point": one line}}.
- "caveats": 1-2 sentences of nuance (what's unclear or debated).
Cite only the message numbers above; never invent chat facts.
"""
    data, _e2 = call_json(p2, GROUNDED_SCHEMA, {"explain": "", "from_chat": [], "caveats": ""})
    return render_grounded(data, index, topic_str)


def render_grounded(data, index, topic_str) -> str:
    if not isinstance(data, dict) or not (data.get("explain") or "").strip():
        return "⚠️ *Analysis failed.*"
    lines = [f"💡 *ELI30: {topic_str[:60]}*", "", data["explain"].strip()]
    cites = [(int(c.get("msg")), (c.get("point") or "").strip())
             for c in data.get("from_chat") or []
             if isinstance(c.get("msg"), (int, float)) and int(c.get("msg")) in index]
    if cites:
        lines += ["", "*From the chat*"]
        for n, point in cites[:5]:
            dt = index[n][0]
            lines.append(f"• {point} _(msg {n}, {dt:%a %H:%M})_")
    if (data.get("caveats") or "").strip():
        lines += ["", f"_{data['caveats'].strip()}_"]
    return "\n".join(lines).strip()


# ── registry ─────────────────────────────────────────────────────────────────

APPROACHES = [
    {
        "name": "asis",
        "title": "Production as-is",
        "desc": "the exact production prompt shipping in wacmd.py today (free text)",
        "hypothesis": "baseline; pleasant prose but no structure, no grounding",
        "llm": True, "window": WINDOW,
        "build": build_asis,
        "render": lambda t: t.strip(),
        "stats": lambda d: {},
    },
    {
        "name": "structured",
        "title": "Structured sections (code render)",
        "desc": "one-liner + analogy + how-it-works points + why it matters + caveats",
        "hypothesis": "scannable and consistent; analogy makes it memorable",
        "llm": True, "window": WINDOW,
        "build": build_structured, "render": render_structured,
        "stats": lambda d: {"points": len((d or {}).get("points") or [])},
    },
    {
        "name": "grounded",
        "title": "Chat-grounded (2 passes, cited)",
        "desc": "pass 1 picks relevant msgs, pass 2 explains + a 'From the chat' section",
        "hypothesis": "ties the explanation to this group's reality; cites make it verifiable",
        "llm": True, "window": WINDOW,
        "custom_run": run_grounded,
        "stats": lambda d: {},
    },
]

BY_NAME = {a["name"]: a for a in APPROACHES}
