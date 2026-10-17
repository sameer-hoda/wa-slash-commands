#!/usr/bin/env python3
"""Sandbox approaches for /stats — team activity & roles.

Axes: baseline (production prompt) · code-first (code computes every number,
model only labels roles) · persona cards (richer free-ish format) · offline
leaderboard (no LLM at all — the control).
"""

import collections
import re

import core
from formatter import fmt_stats

WINDOW = "14d"
DAYS = 14
ROLES = ["The Driver", "The Reviewer", "The Lurker", "The Mediator", "The Escalator"]
HEALTH = ["Active", "Slowing", "Stalled", "Escalating"]

# ── asis: the exact production prompt/schema/render ──────────────────────────


def _activity_asis(ctx):
    counts = collections.Counter()
    for m in ctx["windows"][WINDOW]["messages"]:
        counts[m.get("sender") or "?"] += 1
    return counts


def build_asis(ctx):
    context = core.formatted_window(ctx, WINDOW)
    activity = _activity_asis(ctx)
    total = sum(activity.values())
    activity_json = str(dict(activity.most_common(10))).replace("'", '"')
    prompt = f"""Analyse this WhatsApp chat (last {DAYS} days, {total} msgs total) and produce a team stats JSON.

Activity counts (Name: MessageCount):
{activity_json}

Chat sample (for collaboration style):
{context[:8000]}

Return ONLY valid JSON with:
- "participants": array of up to 5 objects (top senders only), each with:
    "name": string,
    "message_count": integer,
    "share_pct": float (percentage of total),
    "role_tag": exactly one of "The Driver" | "The Reviewer" | "The Lurker" | "The Mediator" | "The Escalator",
    "one_liner": string (max 8 words describing their collaboration style)
- "group_health": exactly one of "Active" | "Slowing" | "Stalled" | "Escalating"
- "bottleneck": string (name of person most likely causing delays, or "None")

Output ONLY valid JSON, no markdown.
"""
    fallback = {
        "participants": [{"name": n, "message_count": c,
                          "share_pct": round(c / total * 100, 1) if total else 0,
                          "role_tag": "The Driver", "one_liner": ""}
                         for n, c in activity.most_common(5)],
        "group_health": "Active",
        "bottleneck": "None",
    }
    schema = {
        "type": "object",
        "properties": {
            "participants": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "message_count": {"type": "integer"},
                        "share_pct": {"type": "number"},
                        "role_tag": {"type": "string", "enum": ROLES},
                        "one_liner": {"type": "string"},
                    },
                    "required": ["name", "message_count", "share_pct", "role_tag", "one_liner"],
                },
            },
            "group_health": {"type": "string", "enum": HEALTH},
            "bottleneck": {"type": "string"},
        },
        "required": ["participants", "group_health", "bottleneck"],
    }
    return prompt, schema, fallback


# ── code-first metrics (shared by codefirst + leaderboard) ───────────────────

GAP_SECS = 3 * 3600


def _metrics(ctx, window: str = WINDOW):
    """Cleaned 14d window → per-sender metrics computed entirely in code."""
    import ledger

    rows = []
    for m in ctx["windows"][window]["messages"]:
        content = (m.get("content") or "").strip()
        if not content or ledger.is_bot_noise(content) or content.lower() in ledger.BANTER:
            continue
        dt = ledger._ist(m["ts"]) if m.get("ts") else None
        if dt is None:
            continue
        sender = m.get("sender") or "?"
        if sender.isdigit():  # senders the fixture could not recover — skip
            continue
        rows.append((dt, sender, content))
    rows.sort(key=lambda r: r[0])

    per = {}
    for dt, sender, content in rows:
        p = per.setdefault(sender, {
            "count": 0, "days": set(), "first": dt, "last": dt,
            "asks": 0, "tags": 0, "links": 0, "night": 0, "chars": 0, "opens": 0,
        })
        p["count"] += 1
        p["days"].add(dt.date().isoformat())
        p["last"] = dt
        if "?" in content:
            p["asks"] += 1
        p["tags"] += len(re.findall(r"@\d+", content))
        if "http" in content:
            p["links"] += 1
        if dt.hour >= 21 or dt.hour < 7:
            p["night"] += 1
        p["chars"] += len(content)

    prev = None
    for dt, sender, _content in rows:
        if prev is not None and (dt - prev).total_seconds() >= GAP_SECS:
            per[sender]["opens"] += 1
        prev = dt

    total = len(rows)
    for p in per.values():
        p["share"] = p["count"] / total * 100 if total else 0
        p["avg_len"] = p["chars"] / p["count"] if p["count"] else 0
    return rows, per, total


def _metrics_table(per) -> str:
    lines = ["name | msgs | share% | active_days | asks | tags | links | night | opens | avg_len"]
    for name, p in sorted(per.items(), key=lambda kv: -kv[1]["count"]):
        lines.append(
            f"{name} | {p['count']} | {p['share']:.0f}% | {len(p['days'])} | {p['asks']} | "
            f"{p['tags']} | {p['links']} | {p['night']} | {p['opens']} | {p['avg_len']:.0f}"
        )
    return "\n".join(lines)


# ── codefirst: code owns numbers, model only labels ──────────────────────────


def _label_schema(people: list) -> dict:
    return {
        "type": "object",
        "properties": {
            "people": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "enum": people},
                        "role_tag": {"type": "string", "enum": ROLES},
                        "one_liner": {"type": "string"},
                    },
                    "required": ["name", "role_tag", "one_liner"],
                },
            },
            "group_health": {"type": "string", "enum": HEALTH},
            "bottleneck": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "why": {"type": "string"}},
                "required": ["name", "why"],
            },
        },
        "required": ["people", "group_health", "bottleneck"],
    }


def run_codefirst(ctx, call_json):
    rows, per, total = _metrics(ctx)
    people = [n for n, _p in sorted(per.items(), key=lambda kv: -kv[1]["count"])]
    sample = core.formatted_window(ctx, WINDOW)[:6000]
    prompt = f"""Label each member of this WhatsApp group from their 14-day activity metrics. The numbers are already computed — do not recompute or contradict them.

Metrics (cleaned, bot noise removed):
{_metrics_table(per)}

Chat sample (for style):
{sample}

For EVERY name in the metrics, return:
- "role_tag": one of {ROLES} — judge from the numbers AND the sample, not from count alone.
- "one_liner": max 8 words on their collaboration style.
Then "group_health" and "bottleneck" ({{"name", "why"}} — who most delays decisions and why, or name "None").
Return ONLY valid JSON.
"""
    data, _err = call_json(prompt, _label_schema(people), {
        "people": [], "group_health": "Active",
        "bottleneck": {"name": "None", "why": ""},
    })
    return render_codefirst(data, per, total)


def render_codefirst(data, per, total) -> str:
    if not isinstance(data, dict):
        return "⚠️ *Analysis failed.*"
    labels = {p.get("name"): p for p in data.get("people") or []}
    lines = [f"📊 *Team Stats — last {DAYS} days*",
             f"_{total} msgs · {len(per)} people · {total / DAYS:.0f}/day_", ""]
    for name, p in sorted(per.items(), key=lambda kv: -kv[1]["count"]):
        lab = labels.get(name) or {}
        role = lab.get("role_tag") or "—"
        one = (lab.get("one_liner") or "").strip()
        lines.append(f"👤 *{name}* — {p['count']} msgs ({p['share']:.0f}%) · "
                     f"{len(p['days'])}/{DAYS} days · {p['asks']} asks · {p['links']} links")
        if one:
            lines.append(f"   _{role} — {one}_")
    health = data.get("group_health") or ""
    if health:
        lines += ["", f"🌡️ *Health:* {health}"]
    b = data.get("bottleneck") or {}
    if (b.get("name") or "None") != "None":
        why = (b.get("why") or "").strip()
        lines.append(f"🚧 *Bottleneck:* {b['name']}" + (f" — {why}" if why else ""))
    return "\n".join(lines)


# ── personas: richer cards with evidence ─────────────────────────────────────

PERSONA_SCHEMA = {
    "type": "object",
    "properties": {
        "people": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "tagline": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "tagline", "evidence"],
            },
        },
        "note": {"type": "string"},
    },
    "required": ["people", "note"],
}


def run_personas(ctx, call_json):
    rows, per, total = _metrics(ctx)
    sample = core.formatted_window(ctx, WINDOW)[:6000]
    prompt = f"""You write short team persona cards for a manager, based on this WhatsApp group's last {DAYS} days.

Metrics (cleaned):
{_metrics_table(per)}

Chat sample:
{sample}

For each active member return:
- "tagline": a 2-4 word persona (e.g. "The Closer", "The Auditor", "Quiet Operator") — must fit the evidence.
- "evidence": ONE concrete line from their actual behaviour (what they do, not praise).
Then "note": one team-level sentence — how this group works and what holds it back.
Return ONLY valid JSON.
"""
    data, _err = call_json(prompt, PERSONA_SCHEMA, {"people": [], "note": ""})
    return render_personas(data, per, total)


def render_personas(data, per, total) -> str:
    if not isinstance(data, dict):
        return "⚠️ *Analysis failed.*"
    counts = {n: p for n, p in per.items()}
    lines = [f"📊 *Team Stats — last {DAYS} days*",
             f"_{total} msgs · a read on how this group actually works_", ""]
    for p in data.get("people") or []:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        meta = counts.get(name)
        meta_str = f" — {meta['count']} msgs ({meta['share']:.0f}%)" if meta else ""
        lines.append(f"*{name}*{meta_str} — _{p.get('tagline', '')}_")
        ev = (p.get("evidence") or "").strip()
        if ev:
            lines.append(f"  {ev}")
    note = (data.get("note") or "").strip()
    if note:
        lines += ["", f"📝 _{note}_"]
    return "\n".join(lines)


# ── leaderboard: offline control (no LLM) ────────────────────────────────────


def run_leaderboard(ctx):
    rows, per, total = _metrics(ctx)
    import ledger

    now = ledger._now(ctx)
    lines = [f"📊 *Team Stats — last {DAYS} days* _(code only, no LLM)_",
             f"_{total} msgs · {len(per)} people · {total / DAYS:.0f}/day_", ""]
    rank = sorted(per.items(), key=lambda kv: -kv[1]["count"])
    active, quiet = [], []
    for name, p in rank:
        if p["count"] >= 5:
            active.append((name, p))
        else:
            quiet.append(f"{name} ({p['count']})")
    for i, (name, p) in enumerate(active, 1):
        lines.append(f"{i}. *{name}* — {p['count']} msgs ({p['share']:.0f}%) · "
                     f"{len(p['days'])}/{DAYS}d · {p['asks']} asks · {p['links']} links · opens {p['opens']}")
    if quiet:
        lines += ["", f"👻 *Quiet:* {', '.join(quiet)}"]

    week = [r for r in rows if (now - r[0]).days < 7]
    prior = [r for r in rows if 7 <= (now - r[0]).days < 14]
    if prior:
        ratio = len(week) / max(1, len(prior))
        trend = "heating up" if ratio > 1.15 else "cooling down" if ratio < 0.85 else "steady"
        lines += ["", f"📈 *Momentum:* last 7d {len(week)} msgs vs prior 7d {len(prior)} — {trend}"]
    return "\n".join(lines)


# ── registry ─────────────────────────────────────────────────────────────────

APPROACHES = [
    {
        "name": "asis",
        "title": "Production as-is",
        "desc": "the exact prompt/schema/render shipping in wacmd.py today",
        "hypothesis": "baseline; model recomputes numbers → drift risk, ignores bottleneck in render",
        "llm": True, "window": WINDOW,
        "build": build_asis, "render": lambda d: fmt_stats(d, DAYS),
        "stats": lambda d: {"people": len((d or {}).get("participants") or [])},
    },
    {
        "name": "codefirst",
        "title": "Code owns numbers, model labels",
        "desc": "metrics computed in code (asks/links/days/opens); model only role_tag + one_liner",
        "hypothesis": "numbers can't drift; roles grounded in real behaviour",
        "llm": True, "window": WINDOW,
        "custom_run": run_codefirst,
        "stats": lambda d: {},
    },
    {
        "name": "personas",
        "title": "Persona cards with evidence",
        "desc": "2-4 word tagline + one concrete behaviour line per person, team note at the end",
        "hypothesis": "most human and shareable; no enum, so roles can get fuzzy",
        "llm": True, "window": WINDOW,
        "custom_run": run_personas,
        "stats": lambda d: {},
    },
    {
        "name": "leaderboard",
        "title": "Offline leaderboard (no LLM)",
        "desc": "pure code: ranking, quiet list, 7d-vs-prior-7d momentum — the control",
        "hypothesis": "zero hallucination, zero cost; no role interpretation at all",
        "llm": False, "window": WINDOW,
        "custom_run": run_leaderboard,
        "stats": lambda d: {},
    },
]

BY_NAME = {a["name"]: a for a in APPROACHES}
