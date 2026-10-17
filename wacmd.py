#!/usr/bin/env python3
"""
wacmd.py
─────────────────────
Standalone slash command handler for WhatsApp bridge.
Invoked by the Go bridge as a CLI:
  python3 wacmd.py <chat_jid> <sender_jid> <command_text>

Features owner-protection mechanics so it only responds to the verified owner JID.
Commands: /sotu  /pending  /stats  /recap  /eli5  /help

Every answer is delivered to the owner's Me chat only (mechat.py resolution) —
the chat the command was typed in is never written to.
"""

import sys
import os
import argparse
import logging
import time
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

# ── Path setup ────────────────────────────────────────────────────────────────
_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
load_dotenv(os.path.join(_dir, ".env"), override=True)

import mechat
import ledger
import engine
from engine import (
    gemini_json, gemini_text,
    cache_read, cache_write,
    get_messages, format_messages_ist, get_activity_stats,
    utc_to_ist, resolve_send_jid,
)
from formatter import fmt_sotu, fmt_pending, fmt_stats, fmt_recap

API_URL = os.getenv("WA_API_URL", "http://127.0.0.1:8090/api/send")
OWNER_PHONE = os.getenv("OWNER_PHONE_NUMBER", "").strip().replace("+", "")
OWNER_JID = f"{OWNER_PHONE}@s.whatsapp.net" if OWNER_PHONE else None

ANALYSIS_COMMANDS = {"/sotu", "/pending", "/stats", "/recap", "/eli5"}

GEMINI_MISSING_TEXT = (
    "⚠️ *Mosaic can't analyse right now* — the Gemini API key is missing.\n"
    "Add `GEMINI_API_KEY` to `.env` (billing-enabled) and retry. `/help` still works."
)
GEMINI_FAILED_TEXT = (
    "⚠️ *Analysis failed* — Gemini returned an error (key/quota?).\n"
    "Nothing was analysed; the logs have the details. Try again."
)


def _analysis_failed(data) -> bool:
    return bool(isinstance(data, dict) and data.get("_gemini_failed"))


def _chat_name(jid: str) -> str:
    try:
        import sqlite3

        con = sqlite3.connect(f"file:{engine.MESSAGES_DB_PATH}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT name FROM chats WHERE jid = ?", (jid,)).fetchone()
        finally:
            con.close()
        return (row[0] if row and row[0] else "") or jid
    except Exception:
        return jid


def _chat_label(jid: str) -> str:
    """Chat display name for titles — empty when it resolves to a raw JID."""
    name = _chat_name(jid)
    return name[:48] if name and "@" not in name else ""

log_path = os.path.join(_dir, "slash_cmd.log")
logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M",
)


# ── WA send ───────────────────────────────────────────────────────────────────

def _print_context_info(msgs, command):
    if not msgs:
        return
    earliest = msgs[0][2]
    latest = msgs[-1][2]
    earliest_str = earliest.strftime("%Y-%m-%d %H:%M") if earliest else "??"
    print(f"📚 [{command}] Context Loaded: {len(msgs):,} messages (Earliest: {earliest_str})")

def send_message(jid: str, text: str) -> None:
    # Resolve @lid JIDs to @s.whatsapp.net before sending.
    send_to = resolve_send_jid(jid)
    headers = {}
    token = mechat.bridge_token()
    if token:
        headers["X-Bridge-Token"] = token
    try:
        resp = requests.post(API_URL, json={"recipient": send_to, "message": text},
                             headers=headers, timeout=10)
        if resp.status_code == 200:
            print(f"✅ Sent to {send_to}" + (f" (resolved from {jid})" if send_to != jid else ""))
        else:
            print(f"⚠️ Send failed {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"❌ Send error: {e}")


def send_answer(text: str) -> None:
    """Deliver a command answer to the owner's Me chat — nowhere else.

    Unresolved or unverifiable Me chat => the answer is dropped with a log
    line. Never a guess, never a group, never the invoking chat.
    """
    target = mechat.get_mechat_jid()
    if not target:
        print("⚠️ Me chat unresolved — answer not sent anywhere.")
        logging.error("mechat unresolved — answer dropped")
        return
    if not mechat.verify_mechat(target):
        print(f"🛡️ Me chat {target} failed verification — answer dropped.")
        logging.error(f"mechat verification failed for {target} — answer dropped")
        return
    send_message(target, text)


def log_invocation(command: str, jid: str, detail: str, latency: float) -> None:
    logging.info(f"{command} for {jid[:20]}… → {detail} [{latency:.1f}s]")


# ── /sotu ─────────────────────────────────────────────────────────────────────
def cmd_sotu(jid: str) -> None:
    t0 = time.time()
    cached = cache_read(jid, "sotu")
    if cached:
        send_answer(fmt_sotu(cached, chat_name=_chat_label(jid)))
        log_invocation("/sotu", jid, "cache hit", time.time() - t0)
        return

    msgs = get_messages(jid, days=30, limit=2000)
    _print_context_info(msgs, "/sotu")
    if not msgs:
        send_answer("⚠️ Not enough history for a State of the Union.")
        return

    context = format_messages_ist(msgs)
    prior = cache_read(jid, "_sotu_prior") or {}
    prior_block = ""
    if prior.get("top_decisions"):
        prior_block = f"""
Previous run summary:
  Decisions: {'; '.join(prior['top_decisions'][:2])}
  Momentum: {prior.get('current_momentum', '')}

Instruction: In 'compared_to_last' describe what is NEW or CHANGED since last run.
"""

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
        "key_ask": ""
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
                        "description": {"type": "string"}
                    },
                    "required": ["title", "description"]
                }
            },
            "recent_happenings": {"type": "string"},
            "key_ask": {"type": "string"}
        },
        "required": ["group_purpose", "big_picture_objective", "key_themes", "recent_happenings", "key_ask"]
    }
    data = gemini_json(prompt, fallback, schema)
    if _analysis_failed(data):
        log_invocation("/sotu", jid, "gemini failed", time.time() - t0)
        send_answer(GEMINI_FAILED_TEXT)
        return
    cache_write(jid, "sotu", data)
    # Save as prior for next run
    cache_write(jid, "_sotu_prior", data)
    send_answer(fmt_sotu(data, chat_name=_chat_label(jid)))
    log_invocation("/sotu", jid, f"{len(data.get('top_decisions',[]))} decisions", time.time() - t0)


# ── /pending ──────────────────────────────────────────────────────────────────
def cmd_pending(jid: str) -> None:
    t0 = time.time()
    msgs = get_messages(jid, days=7, limit=400)
    _print_context_info(msgs, "/pending")
    if not msgs:
        send_answer("⚠️ No recent messages to analyse for pending tasks.")
        return

    text = ledger.render_pending(jid, msgs, chat_name=_chat_name(jid))
    if text is None:
        log_invocation("/pending", jid, "gemini failed (ledger)", time.time() - t0)
        send_answer(GEMINI_FAILED_TEXT)
        return
    cache_write(jid, "pending", {"rendered": text})
    send_answer(text)
    log_invocation("/pending", jid, f"ledger · {len(text)} chars", time.time() - t0)


# ── /stats ────────────────────────────────────────────────────────────────────
def cmd_stats(jid: str, days: int = 14) -> None:
    t0 = time.time()
    cached = cache_read(jid, "stats")
    if cached:
        send_answer(fmt_stats(cached, days, chat_name=_chat_label(jid)))
        log_invocation("/stats", jid, "cache hit", time.time() - t0)
        return

    activity = get_activity_stats(jid, days=days)
    msgs = get_messages(jid, days=days, limit=1000)
    _print_context_info(msgs, "/stats")

    if not activity:
        group_part = _chat_label(jid)
        title = (f"📊 *Team Stats — Last {days} Days — {group_part}*"
                 if group_part else f"📊 *Team Stats — Last {days} Days*")
        send_answer(f"{title}\n\n_No messages found._")
        return

    context = format_messages_ist(msgs)
    total = sum(r[1] for r in activity)
    activity_json = json.dumps({r[0]: r[1] for r in activity[:10]})

    prompt = f"""Analyse this WhatsApp chat (last {days} days, {total} msgs total) and produce a team stats JSON.

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
        "participants": [{"name": r[0], "message_count": r[1], "share_pct": round(r[1]/total*100, 1),
                          "role_tag": "The Driver", "one_liner": ""} for r in activity[:5]],
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
                        "role_tag": {"type": "string", "enum": ["The Driver", "The Reviewer", "The Lurker", "The Mediator", "The Escalator"]},
                        "one_liner": {"type": "string"}
                    },
                    "required": ["name", "message_count", "share_pct", "role_tag", "one_liner"]
                }
            },
            "group_health": {"type": "string", "enum": ["Active", "Slowing", "Stalled", "Escalating"]},
            "bottleneck": {"type": "string"}
        },
        "required": ["participants", "group_health", "bottleneck"]
    }
    data = gemini_json(prompt, fallback, schema)
    if _analysis_failed(data):
        log_invocation("/stats", jid, "gemini failed", time.time() - t0)
        send_answer(GEMINI_FAILED_TEXT)
        return
    cache_write(jid, "stats", data)
    send_answer(fmt_stats(data, days, chat_name=_chat_label(jid)))
    log_invocation("/stats", jid, f"{len(data.get('participants',[]))} participants", time.time() - t0)


# ── /recap ────────────────────────────────────────────────────────────────────
def cmd_recap(jid: str) -> None:
    t0 = time.time()
    msgs = get_messages(jid, days=1, limit=2000)
    _print_context_info(msgs, "/recap")
    if not msgs:
        group_part = _chat_label(jid)
        title = (f"📌 *24h Recap — {group_part}*" if group_part else "📌 *24h Recap*")
        send_answer(f"{title}\n\n_No messages in the last 24 hours._")
        return

    context = format_messages_ist(msgs)

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
                        "action": {"type": "string"}
                    },
                    "required": ["time", "actor", "action"]
                }
            },
            "summary": {"type": "string"}
        },
        "required": ["events", "summary"]
    }
    data = gemini_json(prompt, fallback, schema)
    if _analysis_failed(data):
        log_invocation("/recap", jid, "gemini failed", time.time() - t0)
        send_answer(GEMINI_FAILED_TEXT)
        return
    send_answer(fmt_recap(data, chat_name=_chat_label(jid)))
    log_invocation("/recap", jid, f"{data.get('signal_count',0)} events", time.time() - t0)


# ── /eli5 ─────────────────────────────────────────────────────────────────────
def cmd_eli5(jid: str, topic: str) -> None:
    t0 = time.time()
    msgs = get_messages(jid, days=30, limit=500)
    _print_context_info(msgs, "/eli5")
    context = format_messages_ist(msgs)
    topic_str = topic if topic else "the current conversation context"
    grp_label = _chat_label(jid)
    grp_clause = f" — from *{grp_label}*" if grp_label else ""

    prompt = f"""Explain the following to a 30-year-old professional. Be concise, clear, and professional.

Topic: "{topic_str}"

Use the chat history below for context if the topic refers to something discussed there.

Chat History:
{context}

Format your response for WhatsApp:
- Start with this exact header: 💡 *{topic_str[:60]}*{grp_clause}
- Bold key terms with *asterisks*
- Use _italics_ for caveats or nuance
- Keep to 3-4 short paragraphs max
- No ## headers, no --- dividers, no bullet storms
- Write in plain, direct language — no jargon or filler
"""
    response = gemini_text(prompt)
    send_answer(response)
    log_invocation("/eli5", jid, f"topic={topic_str[:30]}", time.time() - t0)


# ── /help ─────────────────────────────────────────────────────────────────────
HELP_TEXT = """\
*Available Commands:* 🤖

*/sotu* — State of the Union: decisions, risks, momentum (last 30 days).
*/pending* — Open loops by owner: who to chase, how overdue, what's blocked.
*/stats* — Team personas, roles & activity (last 14 days).
*/recap* — 24h timeline: key events only, in IST, noise filtered out.
*/eli5 <topic>* — Explain any topic clearly (professional tone, WA-friendly).
*/help* — This message.\
"""


# ── Main dispatch ─────────────────────────────────────────────────────────────
def _is_owner(sender_jid: str) -> bool:
    """One owner, both spellings (PN or LID), from the pairing store.

    mechat is the single source of truth; the legacy OWNER_PHONE_NUMBER env
    still counts when the session store is unreadable.
    """
    if mechat.is_owner_jid(sender_jid):
        return True
    if OWNER_JID:
        actual_sender = resolve_send_jid(sender_jid)

        # Strip device IDs (the :86 part) to compare the base phone number
        def base_jid(j: str) -> str:
            if not j:
                return j
            parts = j.split("@")
            if len(parts) == 2:
                return f"{parts[0].split(':')[0]}@{parts[1]}"
            return j

        return base_jid(actual_sender) == base_jid(OWNER_JID)
    return False


def handle_command(chat_jid: str, sender_jid: str, command_text: str) -> None:
    # ── SECURITY CHECK: owner only, verified by identity — never "everyone" ──
    if not _is_owner(sender_jid):
        print(f"[🛡️ Security] Ignoring command from non-owner: {sender_jid}")
        return

    parts = command_text.strip().split(" ", 1)
    command = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""

    if command in ANALYSIS_COMMANDS and not engine.ai_available():
        print("[⚠️] GEMINI_API_KEY not set — refusing to answer as if analysis ran.")
        logging.error(f"{command} for {chat_jid[:20]}… — no Gemini key; nothing analysed")
        send_answer(GEMINI_MISSING_TEXT)
        return

    print(f"[v2] {command} for {chat_jid}")

    if command == "/sotu":
        cmd_sotu(chat_jid)
    elif command == "/pending":
        cmd_pending(chat_jid)
    elif command == "/stats":
        cmd_stats(chat_jid, days=14)
    elif command == "/recap":
        cmd_recap(chat_jid)
    elif command == "/eli5":
        cmd_eli5(chat_jid, args)
    elif command == "/help":
        send_answer(HELP_TEXT)
    else:
        # Unknown command — silently ignore (bridge may send non-command messages)
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WhatsApp Slash Command CLI")
    parser.add_argument("chat_jid", help="JID of the chat")
    parser.add_argument("sender_jid", help="JID of the sender")
    parser.add_argument("command", help="Command text (e.g. /sotu)")
    args = parser.parse_args()
    handle_command(args.chat_jid, args.sender_jid, args.command)
