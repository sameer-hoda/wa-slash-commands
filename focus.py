#!/usr/bin/env python3
"""Hourly Top-10 focus digest — the back end behind GET /focus/top10.

Pipeline (ECC cost-aware-llm-pipeline):
  gather (SQLite, code) -> heuristic pre-score (code) -> one flash-lite
  ranking call (LLM) -> stable ids + contract validation (code) ->
  atomic focus.json.

Input = non-archived chats with activity in the last 48h. Archived state
comes from the whatsmeow store (``whatsmeow_chat_settings.archived``), not
from messages.db, which has no archive flag. The Me chat is INCLUDED: the
user's own notes are the strongest signal (SPEC §6.1).

Done-memory: ``done.json`` holds tasks the user marked done in the app.
A done task never regenerates unless its chat has NEWER messages than
``done_at`` — then it returns as a reopened candidate and the model judges
whether there is a genuinely new development.

Cost: one ``gemini-2.5-flash-lite`` JSON call per run (engine.gemini_json),
prompt capped at MAX_PROMPT_CHARS. Spend is estimated (chars/4 tokens) and
logged per run; FOCUS_BUDGET_USD caps a single run (ECC: fail early rather
than overspend). Only transient failures are retried (engine behaviour):
auth/config errors fail fast and keep the previous focus.json.
"""

import datetime
import hashlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
UTC = datetime.timezone.utc

STORE_DIR = os.getenv("STORE_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "store"))
MESSAGES_DB = os.getenv("MESSAGES_DB_PATH", os.path.join(STORE_DIR, "messages.db"))
WHATSAPP_DB = os.getenv("WHATSAPP_DB_PATH", os.path.join(STORE_DIR, "whatsapp.db"))
FOCUS_PATH = os.path.join(STORE_DIR, "focus.json")
DONE_PATH = os.path.join(STORE_DIR, "done.json")
ERROR_PATH = os.path.join(STORE_DIR, "focus_error.json")

WINDOW_HOURS = 48
MAX_CHATS = 15
MAX_MSGS_PER_CHAT = 25
MAX_PROMPT_CHARS = 60000

# ECC: route to the cheapest capable model; flash-lite already is the floor.
MODEL = os.getenv("FOCUS_MODEL", "gemini-2.5-flash-lite")
# flash-lite public pricing ($/1M tokens, input/output). Estimates only.
PRICE_IN, PRICE_OUT = 0.10, 0.40
BUDGET_USD = float(os.getenv("FOCUS_BUDGET_USD", "0.05"))

SOURCES = ("self_note", "ask", "commitment", "deadline", "follow_up")
URGENCIES = ("critical", "high", "normal")

ASK_RE = re.compile(r"\?\s*$|\b(you|your|yours|please|plz|needed|need\b.{0,20}you)\b", re.I)
DEADLINE_RE = re.compile(r"\b(today|tomorrow|tonight|eod|eow|monday|tuesday|wednesday|thursday|friday|deadline|due|by (morning|evening|night|today|tomorrow))\b", re.I)
COMMIT_RE = re.compile(r"\b(i'?ll|i will|i promise|i'?m on it|will send|will share|by tonight|done by)\b", re.I)


# ── ECC immutable cost tracking ─────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class CostRecord:
    model: str
    in_chars: int
    out_chars: int
    est_usd: float


@dataclass(frozen=True, slots=True)
class CostTracker:
    budget_limit: float = BUDGET_USD
    records: tuple = ()

    def add(self, record: CostRecord) -> "CostTracker":
        return CostTracker(budget_limit=self.budget_limit, records=(*self.records, record))

    @property
    def total_cost(self) -> float:
        return sum(r.est_usd for r in self.records)

    @property
    def over_budget(self) -> bool:
        return self.total_cost > self.budget_limit


class BudgetExceeded(Exception):
    pass


def estimate_cost(model: str, prompt: str, out_text: str) -> CostRecord:
    in_tok, out_tok = len(prompt) / 4, len(out_text) / 4
    usd = in_tok / 1e6 * PRICE_IN + out_tok / 1e6 * PRICE_OUT
    return CostRecord(model=model, in_chars=len(prompt), out_chars=len(out_text), est_usd=usd)


# ── gather ──────────────────────────────────────────────────────────────────

def _open_ro(path):
    if not os.path.exists(path):
        return None
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def archived_jids():
    """JIDs the user archived in WhatsApp (whatsmeow store)."""
    con = _open_ro(WHATSAPP_DB)
    if con is None:
        return set()
    try:
        rows = con.execute(
            "SELECT chat_jid FROM whatsmeow_chat_settings WHERE archived = 1"
        ).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()
    finally:
        con.close()


def own_jid_forms():
    """All JID spellings of the owner's self chat."""
    try:
        import mechat
        phone, lid, _ = mechat.own_identity()
    except Exception:
        return set()
    out = set()
    for ident in filter(None, [phone, lid]):
        out.add(f"{ident}@s.whatsapp.net")
        out.add(f"{ident}@lid")
    return out


def _parse_ts(raw):
    try:
        dt = datetime.datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def recent_chats(now, upper=None):
    """Chats with activity in the window: jid -> {name, msgs, last_ts}.

    upper caps message timestamps (time-travel experiments): when set,
    nothing newer than upper is visible — no future leakage.

    Timestamp filtering is strict in Python (parsed datetimes). SQLite does
    a loose pre-filter only, in the stored timestamps' own space-separated
    shape ("2026-10-27 20:56:33+05:30") so the comparison stays chronological.

    Candidate chats come from the MESSAGES table, never from
    chats.last_message_time, which goes stale on backfilled history and
    would silently hide active chats.
    """
    con = _open_ro(MESSAGES_DB)
    if con is None:
        return {}
    try:
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        cutoff_dt = now - datetime.timedelta(hours=WINDOW_HOURS)
        if isinstance(upper, str):
            upper_dt = _parse_ts(upper)
        else:
            upper_dt = upper or now
        if upper_dt is not None and upper_dt.tzinfo is None:
            upper_dt = upper_dt.replace(tzinfo=UTC)
        loose_lo = (cutoff_dt - datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        archived = archived_jids()
        names = {}
        try:
            for r in con.execute("SELECT jid, name FROM chats").fetchall():
                names[r["jid"]] = r["name"] or r["jid"]
        except Exception:
            pass
        chats = {}
        for r in con.execute(
            "SELECT DISTINCT chat_jid FROM messages WHERE timestamp >= ?", (loose_lo,)
        ).fetchall():
            if r["chat_jid"] in archived:
                continue
            chats[r["chat_jid"]] = {"name": names.get(r["chat_jid"], r["chat_jid"]),
                                    "msgs": [], "last_ts": ""}
        if not chats:
            return {}
        q = ",".join("?" for _ in chats)
        for r in con.execute(
            f"""SELECT chat_jid, sender, content, timestamp, is_from_me FROM messages
                WHERE chat_jid IN ({q}) AND timestamp >= ?
                ORDER BY timestamp DESC""",
            (*chats.keys(), loose_lo),
        ).fetchall():
            c = chats.get(r["chat_jid"])
            if c is None or len(c["msgs"]) >= MAX_MSGS_PER_CHAT * 3:
                continue
            ts = _parse_ts(r["timestamp"])
            if ts is None or ts < cutoff_dt or ts > upper_dt:
                continue
            text = (r["content"] or "").strip()
            if not text:
                continue
            try:
                import ledger
                if ledger.is_bot_noise(text):
                    continue
            except Exception:
                pass
            c["msgs"].append({
                "sender": r["sender"] or "",
                "me": bool(r["is_from_me"]),
                "text": text[:500],
                "ts": r["timestamp"] or "",
            })
            if not c["last_ts"]:
                c["last_ts"] = r["timestamp"] or ""
        return {jid: c for jid, c in chats.items() if c["msgs"]}
    finally:
        con.close()


# ── heuristic pre-score (code, no LLM) ─────────────────────────────────────

def chat_score(chat, now, self_jids):
    """Rank chats for prompt inclusion. Rewards what the user asked for:
    recent activity first, then chats the user participates in, then
    explicit demand signals. Self chat always qualifies (self-note fuel)."""
    msgs = chat["msgs"]
    n = len(msgs)
    mine = sum(1 for m in msgs if m["me"])
    try:
        last = datetime.datetime.fromisoformat(chat["last_ts"])
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        age_h = max(0.0, (now - last).total_seconds() / 3600)
    except Exception:
        age_h = WINDOW_HOURS
    recency = max(0.0, 1.0 - age_h / WINDOW_HOURS)
    text = "\n".join(m["text"] for m in msgs[:MAX_MSGS_PER_CHAT])
    asks = len(ASK_RE.findall(text))
    deadlines = len(DEADLINE_RE.findall(text))
    commits = len(COMMIT_RE.findall(text))
    score = (
        3.0 * recency
        + 2.0 * min(1.0, mine / 3.0)          # user has messages here
        + 0.3 * min(asks, 5)
        + 0.5 * min(deadlines, 4)
        + 0.4 * min(commits, 4)
        + 0.2 * min(n / 10.0, 1.0)
    )
    return score


def pick_chats(chats, now, self_jids):
    ranked = sorted(chats.items(), key=lambda kv: chat_score(kv[1], now, self_jids), reverse=True)
    # Self chat always rides along (top signal per SPEC §6.1).
    picks = []
    for jid, chat in ranked:
        if jid in self_jids and jid not in picks:
            picks.append(jid)
    for jid, _ in ranked:
        if jid not in picks:
            picks.append(jid)
    return picks[:MAX_CHATS]


# ── done memory ─────────────────────────────────────────────────────────────

def load_done():
    try:
        with open(DONE_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_done(done):
    tmp = DONE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(done, f, indent=1)
    os.replace(tmp, DONE_PATH)


def mark_done(item_id, title="", chat_jid="", last_activity=""):
    """Called by POST /focus/done when the user marks a task done in the app.
    The app sends id "forget:<id>" on undo — that deletes the done-mark so
    the next refresh may return the item."""
    done = load_done()
    if item_id.startswith("forget:"):
        done.pop(item_id[len("forget:"):], None)
        save_done(done)
        return done
    done[item_id] = {
        "title": title,
        "chat_jid": chat_jid,
        "done_at": datetime.datetime.now(UTC).isoformat(),
        "last_activity": last_activity,
    }
    save_done(done)
    return done


def reopened_notes(picks, chats, done):
    """Done tasks whose chats have NEWER messages: candidates the model may
    resurface only on genuinely new developments."""
    notes = []
    for jid in picks:
        last = chats[jid]["last_ts"]
        for item_id, d in done.items():
            if d.get("chat_jid") != jid or not d.get("done_at"):
                continue
            try:
                if last and last > d["done_at"] and (not d.get("last_activity") or last > d["last_activity"]):
                    notes.append(
                        f'- "{d.get("title", "?")}" was marked done {d["done_at"][:10]}; '
                        f"chat has newer messages ({last[:16]}). Resurface ONLY if they "
                        f"change the outcome, reopen the task, or add a new ask."
                    )
            except Exception:
                continue
    return notes


# ── stable ids + contract validation (code owns both) ──────────────────────

def canon_jid(jid, picks):
    """Canonicalize a model-returned jid against the ranked chat set.

    Output hygiene (same class as contract validation): the model sometimes
    returns a right-conversation/wrong-spelling jid (bare phone, @lid vs
    @s.whatsapp.net). Map digit-identical 1:1 identifiers to the canonical
    pick; groups and broadcast require exact matches. Unmatched -> None,
    which the UI renders without a deep link rather than a wrong one.
    """
    jid = (jid or "").strip()
    if jid in picks:
        return jid
    if not jid or jid.endswith("@g.us") or jid == "status@broadcast":
        return None
    digits = re.sub(r"\D", "", jid)
    if not digits:
        return None
    matches = [p for p in picks
               if not p.endswith("@g.us") and p != "status@broadcast"
               and re.sub(r"\D", "", p) == digits]
    if len(matches) == 1:
        return matches[0]
    return None


def stable_id(chat_jid, title):
    norm = re.sub(r"\s+", " ", (title or "").strip().lower())
    return hashlib.sha1(f"{chat_jid}\x00{norm}".encode()).hexdigest()[:12]


def validate_digest(doc):
    """Mirror of docs/focus-kit/focus.schema.json. Returns (ok, error)."""
    if not isinstance(doc, dict):
        return False, "top level must be an object"
    for k in ("generated_at", "headline", "items"):
        if k not in doc:
            return False, f"missing {k}"
    items = doc["items"]
    if not isinstance(items, list) or len(items) > 10:
        return False, "items must be a list of at most 10"
    seen_ranks, seen_ids, critical = set(), set(), 0
    allowed = {"id", "rank", "title", "why", "chat_name", "chat_jid",
               "source", "urgency", "due", "waiting_on", "last_activity"}
    for it in items:
        if not isinstance(it, dict) or set(it) - allowed:
            return False, "item has unknown fields"
        for k in ("id", "rank", "title", "why", "chat_name", "chat_jid",
                  "source", "urgency", "waiting_on"):
            if k not in it:
                return False, f"item missing {k}"
        if not (1 <= it["rank"] <= 10) or it["rank"] in seen_ranks:
            return False, "rank must be unique 1..10"
        seen_ranks.add(it["rank"])
        if it["id"] in seen_ids:
            return False, "duplicate id"
        seen_ids.add(it["id"])
        if not (isinstance(it["title"], str) and 0 < len(it["title"]) <= 60):
            return False, "title must be 1..60 chars"
        if not (isinstance(it["why"], str) and 0 < len(it["why"]) <= 100):
            return False, "why must be 1..100 chars"
        if it["source"] not in SOURCES:
            return False, f"bad source {it['source']}"
        if it["urgency"] not in URGENCIES:
            return False, f"bad urgency {it['urgency']}"
        if it["urgency"] == "critical":
            critical += 1
        if it["waiting_on"] not in ("you", "them"):
            return False, "bad waiting_on"
    if critical > 3:
        return False, "at most 3 critical"
    return True, ""


# ── prompt + rank ───────────────────────────────────────────────────────────

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "why": {"type": "string"},
                    "chat_name": {"type": "string"},
                    "chat_jid": {"type": "string"},
                    "source": {"type": "string", "enum": list(SOURCES)},
                    "urgency": {"type": "string", "enum": list(URGENCIES)},
                    "due": {"type": "string"},
                    "waiting_on": {"type": "string", "enum": ["you", "them"]},
                    "last_activity": {"type": "string"},
                },
                "required": ["title", "why", "chat_name", "chat_jid", "source", "urgency", "waiting_on"],
            },
        },
    },
    "required": ["headline", "items"],
}


DEFAULT_RULES = """Rules: the owner's Me-chat notes are the strongest signal; then direct asks, commitments, explicit deadlines, threads waiting on someone else. Drop resolved threads and banter. At most 10 items, at most 3 critical. Title ≤ 60 chars imperative starting with a verb; why ≤ 100 chars of consequence, not a quote. Chat_jid: copy the [jid] shown for the chat; groups without one use null; never invent ids. DUE DATES come from message TEXT mentioning a date, NEVER from timestamps or metadata; omit if none named. HEADLINE is one editorial line naming the bottleneck, never "Top 10 ...".
DIVERSITY PROTOCOL (do this visibly, it is part of the answer): after drafting the list, write a COUNT line tallying items per chat, e.g. COUNTS: Seeti=4, CRED=3, OKR=2. If any chat owns more than 3, delete its weakest beyond 3 and backfill from the best item of a chat with none. Recount and confirm every chat ≤3 BEFORE finalizing. A list violating this is WRONG — repair it, don't explain it. (Lab champion baseline3, rounds 3-4: auto 0.639, best diversity.)"""

VARIANT_RULES = {
    # Round-1 brains: same data, different ranking philosophies. The lab
    # swaps ONLY this block — no mechanical/regex scoring changes.
    "baseline": DEFAULT_RULES,
    "outcome": """Rank like a chief of staff who is judged ONLY on outcomes that moved. Order by: explicit deadlines first (soonest due wins), then the owner's own commitments ("I'll send it tonight"), then direct asks, then everything else. Penalize banter, status chatter, and FYIs to the bottom or drop them. Self-notes count only if they name a concrete next action. Same output contract as the default rules.""",
    "voice": """The owner's own voice dominates: Me-chat notes and messages the owner SENT are the strongest signal — an obligation the owner wrote down outranks anything anyone asked for. Next: direct asks of the owner by name. Deprioritize threads waiting on other people ("waiting on them" goes last) and group chatter the owner never joined. Same output contract as the default rules.""",
    "regret": """Ask of every candidate: "what would the owner regret ignoring come Friday?" Rank by regret times irreversibility: missed money, broken promises, blocked launches, commitments with named dates first. Chat_jid: copy the [jid] shown; groups without one use null; never invent ids. DUE DATES come from message TEXT only, never metadata. HEADLINE names the single biggest risk.
DIVERSITY PROTOCOL (do this visibly, it is part of the answer): after drafting, write a COUNT line tallying items per chat. If any chat owns more than 2, keep only its two strongest and backfill from uncovered chats. Recount and confirm ≤2 each BEFORE finalizing. A list violating this is WRONG — repair it, don't explain it. (Lab co-champion regret3, rounds 2-4: auto 0.639.)""",
}


def build_prompt(picks, chats, done, reopen_notes, rules=None):
    lines = []
    for jid in picks:
        c = chats[jid]
        lines.append(f"\n### {c['name']} [{jid}] (last: {c['last_ts'][:16]})")
        for m in list(reversed(c["msgs"][:MAX_MSGS_PER_CHAT])):
            who = "ME" if m["me"] else (m["sender"] or "?")
            lines.append(f"[{m['ts'][:16]}] {who}: {m['text']}")
    done_block = ""
    if done:
        ds = [f'- "{d.get("title", "?")}" (done {d.get("done_at", "")[:10]})' for d in done.values()]
        done_block = ("Tasks already marked DONE — never regenerate these unless a "
                      "reopened note below says otherwise:\n" + "\n".join(ds[:50]) + "\n\n")
    reopen_block = ("Reopened candidates (new messages since done — resurface ONLY on "
                    "genuinely new developments):\n" + "\n".join(reopen_notes) + "\n\n") if reopen_notes else ""
    rules = rules or DEFAULT_RULES
    prompt = f"""You are a sharp executive chief of staff. Rank the owner's 10 most important open work items from the last 48 hours of WhatsApp.

{rules}

{done_block}{reopen_block}Chats:
{"".join(lines)[:MAX_PROMPT_CHARS]}

Return ONLY valid JSON: {{"headline": "...", "items": [{{"title", "why", "chat_name", "chat_jid", "source", "urgency", "due", "waiting_on", "last_activity"}}]}}"""
    return prompt


def rank_once(rules=None, now=None, upper=None):
    """Run one ranking pass. Returns (digest, tracker). Raises on failure —
    the caller keeps the previous focus.json (fail loud, never fake).

    rules swaps the ranking philosophy (tuning lab); now/upper time-travel
    the 48h window (upper caps visible messages — no future leakage).
    """
    import engine

    now = now or datetime.datetime.now(UTC)
    self_jids = own_jid_forms()
    chats = recent_chats(now, upper=upper)
    if not chats:
        raise RuntimeError("no-chats: no chats with 48h activity")
    picks = pick_chats(chats, now, self_jids)
    done = load_done()
    notes = reopened_notes(picks, chats, done)
    prompt = build_prompt(picks, chats, done, notes, rules=rules)

    tracker = CostTracker()
    if tracker.over_budget:  # zero-record tracker can only be over with budget<=0
        raise BudgetExceeded(tracker.total_cost, tracker.budget_limit)
    data = engine.gemini_json(prompt, {"headline": "", "items": []}, RESPONSE_SCHEMA)
    if data.get("_gemini_failed"):
        raise RuntimeError("gemini: gemini call failed (key missing/invalid or API down)")
    tracker = tracker.add(estimate_cost(MODEL, prompt, json.dumps(data)))
    if tracker.over_budget:
        raise BudgetExceeded(tracker.total_cost, tracker.budget_limit)
    print(f"[focus] model={MODEL} prompt_chars={len(prompt)} est_usd={tracker.total_cost:.4f}")

    doc = {
        "generated_at": now.isoformat(),
        "headline": (data.get("headline") or "").strip()[:90],
        "items": [],
    }
    for i, it in enumerate((data.get("items") or [])[:10], 1):
        jid = canon_jid(it.get("chat_jid"), picks) or None
        name = next((chats[j]["name"] for j in picks if j == jid), (it.get("chat_name") or "").strip()) if jid else (it.get("chat_name") or "").strip()
        due = it.get("due") or None
        # Output hygiene (same class as contract validation, not ranking
        # logic): null any "deadline" that is just the message timestamp
        # laundered into the due field. A due must come from message TEXT.
        if due and it.get("last_activity"):
            try:
                if _parse_ts(due) == _parse_ts(it["last_activity"]):
                    due = None
            except Exception:
                pass
        doc["items"].append({
            "id": stable_id(jid, it.get("title", "")),
            "rank": i,
            "title": (it.get("title") or "")[:60],
            "why": (it.get("why") or "")[:100],
            "chat_name": name,
            "chat_jid": jid or None,
            "source": it.get("source"),
            "urgency": it.get("urgency"),
            "due": due,
            "waiting_on": it.get("waiting_on"),
            "last_activity": it.get("last_activity") or None,
        })
    ok, err = validate_digest(doc)
    if not ok:
        raise RuntimeError(f"contract: model output failed validation: {err}")
    tmp = FOCUS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=1)
    os.replace(tmp, FOCUS_PATH)
    return doc, tracker


def write_error(reason, detail):
    """Persist the failure reason for /focus/top10 (best-effort)."""
    try:
        tmp = ERROR_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"reason": reason, "detail": detail,
                       "at": datetime.datetime.now(UTC).isoformat()}, f)
        os.replace(tmp, ERROR_PATH)
    except OSError:
        pass


def main(argv):
    if "--mark-done" in argv:
        i = argv.index("--mark-done")

        def arg(n):
            return argv[i + 1 + n] if i + 1 + n < len(argv) else ""

        mark_done(arg(0), title=arg(1), chat_jid=arg(2), last_activity=arg(3))
        print(f"[focus] marked done {arg(0)}")
        return 0
    if "--validate" in argv:
        i = argv.index("--validate")
        with open(argv[i + 1]) as f:
            doc = json.load(f)
        ok, err = validate_digest(doc)
        print("valid" if ok else f"INVALID: {err}")
        return 0 if ok else 1
    if "--chats" in argv:
        now = datetime.datetime.now(UTC)
        chats = recent_chats(now)
        picks = pick_chats(chats, now, own_jid_forms())
        for jid in picks:
            c = chats[jid]
            print(f"{chat_score(c, now, own_jid_forms()):5.2f}  {c['name'][:30]:30s}  msgs={len(c['msgs'])}  last={c['last_ts'][:16]}")
        return 0
    try:
        doc, tracker = rank_once()
    except BudgetExceeded as e:
        write_error("budget", f"run budget exceeded: {e}")
        print(f"[focus] rank failed (keeping previous focus.json): {e}")
        return 1
    except Exception as e:
        msg = str(e)
        reason = msg.split(":", 1)[0] if msg.split(":", 1)[0] in ("no-chats", "gemini", "contract") else "unknown"
        write_error(reason, msg)
        print(f"[focus] rank failed (keeping previous focus.json): {e}")
        return 1
    try:
        os.remove(ERROR_PATH)
    except OSError:
        pass
    print(f"[focus] wrote {FOCUS_PATH} with {len(doc['items'])} items, est ${tracker.total_cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
