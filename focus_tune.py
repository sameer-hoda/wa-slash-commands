#!/usr/bin/env python3
"""Time-travel tuning lab for the Focus Top-10 (ECC cost-aware, blinded).

Compares prompt brains (not mechanical rules) on identical 48h windows from
the owner's past, scored against what the owner actually did next.

    python3 focus_tune.py survey                  # pick cutoffs with data
    python3 focus_tune.py run --round 1 --cutoffs 24,72
    python3 focus_tune.py rate --round 1           # blinded 1-5 ratings
    python3 focus_tune.py score --round 1          # auto + human leaderboard

Ground truth = the owner's own sent messages in the 24h AFTER each cutoff
(revealed preference: which chats he actually engaged). No post-cutoff
message is ever visible to a ranking run (strict upper bound in focus.py).

Costs: one flash-lite call per (cutoff, variant) cell, logged per run.
Results live in /tmp/focuslab (personal chat data — never commit).
"""
import datetime
import hashlib
import json
import os
import random
import sqlite3
import subprocess
import sys

UTC = datetime.timezone.utc
LAB_DIR = "/tmp/focuslab"
ENGAGE_AFTER_H = 24


def utcnow():
    return datetime.datetime.now(UTC)


def ensure_key():
    if os.getenv("GEMINI_API_KEY"):
        return
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", "com.sameerhoda.mosaic",
             "-a", "gemini-api-key", "-w"],
            capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            os.environ["GEMINI_API_KEY"] = out.stdout.strip()
            return
    except Exception:
        pass
    sys.exit("error: set GEMINI_API_KEY (or approve the Keychain prompt and re-run)")


def db():
    mdb = os.getenv("MESSAGES_DB_PATH", os.path.expanduser(
        "~/Library/Application Support/Mosaic/messages.db"))
    con = sqlite3.connect(f"file:{mdb}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def parse_ts(raw):
    try:
        dt = datetime.datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def window_stats(con, cutoff):
    """(chats, msgs, user_msgs) in [cutoff-48h, cutoff]. Pure-SQL loose scan."""
    lo = (cutoff - datetime.timedelta(hours=54)).isoformat()
    hi = (cutoff + datetime.timedelta(hours=1)).isoformat()
    rows = con.execute(
        "SELECT chat_jid, content, timestamp, is_from_me FROM messages "
        "WHERE timestamp >= ? AND timestamp <= ?", (lo, hi)).fetchall()
    chats, msgs, mine = set(), 0, 0
    for r in rows:
        ts = parse_ts(r["timestamp"])
        if ts is None or ts < cutoff - datetime.timedelta(hours=48) or ts > cutoff:
            continue
        if not (r["content"] or "").strip():
            continue
        chats.add(r["chat_jid"])
        msgs += 1
        mine += bool(r["is_from_me"])
    return len(chats), msgs, mine


def engaged_after(con, cutoff):
    """Chats where the owner SENT a message in (cutoff, cutoff+24h]."""
    lo, hi = cutoff.isoformat(), (cutoff + datetime.timedelta(hours=ENGAGE_AFTER_H)).isoformat()
    rows = con.execute(
        "SELECT DISTINCT chat_jid FROM messages WHERE is_from_me = 1 "
        "AND timestamp > ? AND timestamp <= ?", (lo, hi)).fetchall()
    got = {r[0] for r in rows}
    # String-boundary fuzz (space-vs-T shapes): verify in Python.
    out = set()
    for jid in got:
        ts_rows = con.execute(
            "SELECT timestamp FROM messages WHERE chat_jid = ? AND is_from_me = 1 "
            "AND timestamp > ? AND timestamp <= ?", (jid, lo, hi)).fetchall()
        if any((parse_ts(r[0]) or cutoff) > cutoff for r in ts_rows):
            out.add(jid)
    return out


def canon_lab(jid):
    """Identity for scoring: LID/phone spellings of one conversation merge;
    group JIDs stay exact. Mirrors focus.canon_jid's 1:1 rule."""
    import re
    jid = (jid or "").strip()
    if jid.endswith("@g.us") or jid == "status@broadcast":
        return jid
    return re.sub(r"\D", "", jid) or jid


def score_digest(items, engaged):
    """Weighted recall of engaged chats + coverage. Pure function.

    MRR rewards the FIRST engaged chat high in the list; coverage rewards
    breadth. Both in [0,1]. Identity is canonicalized so @lid vs
    @s.whatsapp.net spellings of one conversation don't split credit.
    """
    eng = {canon_lab(j) for j in engaged}
    ranks = [it["rank"] for it in items if canon_lab(it.get("chat_jid")) in eng]
    mrr = (1.0 / min(ranks)) if ranks else 0.0
    hit_chats = {canon_lab(it["chat_jid"]) for it in items if canon_lab(it.get("chat_jid")) in eng}
    coverage = len(hit_chats) / len(eng) if eng else 0.0
    return {"mrr": round(mrr, 3), "coverage": round(coverage, 3),
            "auto": round(0.6 * mrr + 0.4 * coverage, 3)}


LAB_RULES = {
    # Lab-only brains (production keeps VARIANT_RULES until a winner ships).
    # Round-2 mutations from round-1 failures. Same data, prompt-only changes.
    "baseline2": """Rules: the owner's Me-chat notes are the strongest signal; then direct asks, commitments, explicit deadlines, threads waiting on someone else. Drop resolved threads and banter. At most 10 items, at most 3 critical. Title ≤ 60 chars imperative starting with a verb; why ≤ 100 chars of consequence, never a quote. Chat_jid from the [jid] shown; no invented ids.
DIVERSITY SELF-CHECK (mandatory, before finalizing): count items per chat. If any chat owns more than 3, delete its weakest beyond 3 and promote the best item from a chat with none. A Top 10 from 1-2 chats is a FAILED list — fix it before answering.
DUE DATES come from message TEXT mentioning a date ("tonight", "Friday", "EOD"), NEVER from timestamps or metadata. If no date is named, omit due.
HEADLINE: one editorial line naming the bottleneck, e.g. "Launch is gated on the deck". Never "Top 10 ... (Last 48 Hours)".""",
    "voice2": """The owner's own words carry the most weight: obligations the owner wrote in the Me chat or stated themselves outrank anything asked of them; direct asks of the owner by name come next. TAXONOMY IS STRICT: source "self_note" is ONLY for Me-chat items — everything else is ask/commitment/deadline/follow_up by what actually happened. waiting_on is "you" when the OWNER must act next, "them" only when genuinely blocked on someone else. Deprioritize group chatter the owner never joined. Same output contract: ≤60-char imperative titles, ≤100-char whys, dues from message text only, no invented ids.""",
    "regret2": """Ask of every candidate: "what would the owner regret ignoring come Friday?" Rank by regret times irreversibility: missed money, broken promises, blocked launches, commitments with named dates first. DIVERSITY SELF-CHECK (mandatory, before finalizing): at most 2 items from any single chat — if a third qualifies, keep only the two strongest and backfill from uncovered chats. DUE DATES come from message TEXT only, never metadata. HEADLINE names the single biggest risk, e.g. "Seeti launch will slip without the deck". Same output contract otherwise.""",
    "baseline3": """Rules: the owner's Me-chat notes are the strongest signal; then direct asks, commitments, explicit deadlines, threads waiting on someone else. Drop resolved threads and banter. At most 10 items, at most 3 critical. Title ≤ 60 chars imperative starting with a verb; why ≤ 100 chars of consequence, not a quote. DUE DATES come from message TEXT mentioning a date, NEVER from timestamps or metadata; omit if none named. HEADLINE is one editorial line naming the bottleneck, never "Top 10 ...".
DIVERSITY PROTOCOL (do this visibly, it is part of the answer): after drafting the list, write a COUNT line tallying items per chat, e.g. COUNTS: Seeti=4, CRED=3, OKR=2. If any chat owns more than 3, delete its weakest beyond 3 and backfill from the best item of a chat with none. Recount and confirm every chat ≤3 BEFORE finalizing. A list violating this is WRONG — repair it, don't explain it.""",
    "regret3": """Ask of every candidate: "what would the owner regret ignoring come Friday?" Rank by regret times irreversibility: missed money, broken promises, blocked launches, commitments with named dates first. DUE DATES come from message TEXT only, never metadata. HEADLINE names the single biggest risk.
DIVERSITY PROTOCOL (do this visibly, it is part of the answer): after drafting, write a COUNT line tallying items per chat. If any chat owns more than 2, keep only its two strongest and backfill from uncovered chats. Recount and confirm ≤2 each BEFORE finalizing. A list violating this is WRONG — repair it, don't explain it.""",
}


def rules_for(variant):
    if variant in LAB_RULES:
        return LAB_RULES[variant]
    import focus
    return focus.VARIANT_RULES[variant]


def assign_labels(variants, seed):
    """Blinded A/B/… labels, deterministic per seed. Mapping saved, never shown."""
    rng = random.Random(f"{seed}")
    order = sorted(variants, key=lambda _: rng.random())
    return {chr(65 + i): v for i, v in enumerate(order)}


def cmd_survey(args):
    con = db()
    now = utcnow()
    print(f"{'cutoff':>8} {'window chats':>12} {'msgs':>7} {'mine':>6}  engaged-next-24h")
    for h in [12, 24, 48, 72, 96]:
        t = now - datetime.timedelta(hours=h)
        c, m, mine = window_stats(con, t)
        e = engaged_after(con, t)
        print(f"{h:>6}h {c:>12} {m:>7} {mine:>6}  {len(e)} chats")
    print("pick 2 cutoffs with a healthy window AND some next-day engagement.")


def cmd_run(args):
    ensure_key()
    import focus  # noqa: E402  (needs env first)
    _r = args[args.index("--round") + 1] if "--round" in args else "1"
    rnd = int(str(_r).removeprefix("round"))
    cutoffs = [int(x) for x in args[args.index("--cutoffs") + 1].split(",")] if "--cutoffs" in args else [24, 72]
    variants = (args[args.index("--variants") + 1].split(",")
                if "--variants" in args else ["baseline", "outcome", "voice", "regret"])
    seed = args[args.index("--seed") + 1] if "--seed" in args else "r1"
    now = utcnow()
    rdir = os.path.join(LAB_DIR, f"round{rnd}")
    os.makedirs(rdir, exist_ok=True)
    total, spent = 0, 0.0
    for h in cutoffs:
        t = now - datetime.timedelta(hours=h)
        cdir = os.path.join(rdir, f"T-{h}h")
        os.makedirs(cdir, exist_ok=True)
        for v in variants:
            out = os.path.join(cdir, f"{v}.json")
            if os.path.exists(out):
                print(f"  skip T-{h}h/{v} (already run)")
                continue
            print(f"  rank T-{h}h/{v} ...", flush=True)
            try:
                doc, tracker = focus.rank_once(
                    rules=rules_for(v), now=t, upper=t.isoformat())
                spent += tracker.total_cost
                total += 1
                with open(out, "w") as f:
                    json.dump({"variant": v, "cutoff_h": h,
                               "cutoff_at": t.isoformat(),
                               "est_usd": tracker.total_cost,
                               "digest": doc}, f, indent=1)
                print(f"    ok ({len(doc['items'])} items, est ${tracker.total_cost:.4f})")
            except Exception as e:
                with open(out, "w") as f:
                    json.dump({"variant": v, "cutoff_h": h, "error": str(e)}, f, indent=1)
                print(f"    FAILED: {e}")
    with open(os.path.join(rdir, "_blind.json"), "w") as f:
        json.dump({"seed": seed,
                   "labels": {c: assign_labels(variants, f"{seed}:{c}") for c in
                              [f"T-{h}h" for h in cutoffs]}}, f, indent=1)
    print(f"done: {total} cells, est ${spent:.4f}. Next: python3 focus_tune.py rate --round {rnd}")


def load_cell(rdir, cutoff, variant):
    with open(os.path.join(rdir, cutoff, f"{variant}.json")) as f:
        return json.load(f)


def cmd_rate(args):
    _r = args[args.index("--round") + 1] if "--round" in args else "1"
    rnd = int(str(_r).removeprefix("round"))
    rdir = os.path.join(LAB_DIR, f"round{rnd}")
    blind = json.load(open(os.path.join(rdir, "_blind.json")))["labels"]
    ratings = {}
    for cutoff, mapping in blind.items():
        print(f"\n=== window ending {cutoff} (48h of chats, ranked blind) ===")
        for label in sorted(mapping):
            cell = load_cell(rdir, cutoff, mapping[label])
            print(f"\n--- option {label} ---")
            if "error" in cell:
                print(f"  (failed to rank: {cell['error']})")
                continue
            for it in cell["digest"]["items"]:
                print(f"  {it['rank']:2d}. {it['title']}  [{it['urgency']}/{it['source']}]")
                print(f"      {it['why']}  — {it['chat_name']}")
        while True:
            raw = input(f"Rate {','.join(sorted(mapping))} 1-5 (space-separated): ").strip().split()
            if len(raw) == len(mapping) and all(x.isdigit() and 1 <= int(x) <= 5 for x in raw):
                break
            print("  need one 1-5 rating per option, e.g. 4 3 5 2")
        ratings[cutoff] = {label: int(raw[i]) for i, label in enumerate(sorted(mapping))}
        ratings[cutoff]["_note"] = input("  note (optional, Enter to skip): ").strip()
    with open(os.path.join(rdir, "ratings.json"), "w") as f:
        json.dump(ratings, f, indent=1)
    print("saved. Next: python3 focus_tune.py score --round", rnd)


def cmd_score(args):
    _r = args[args.index("--round") + 1] if "--round" in args else "1"
    rnd = int(str(_r).removeprefix("round"))
    rdir = os.path.join(LAB_DIR, f"round{rnd}")
    blind = json.load(open(os.path.join(rdir, "_blind.json")))
    ratings = {}
    try:
        ratings = json.load(open(os.path.join(rdir, "ratings.json")))
    except OSError:
        pass
    con = db()
    totals, counts = {}, {}
    for cutoff, mapping in blind["labels"].items():
        h = int(cutoff.split("-")[1].rstrip("h"))
        t = utcnow() - datetime.timedelta(hours=h)
        engaged = engaged_after(con, t)
        print(f"\n=== {cutoff}: {len(engaged)} chats engaged next day ===")
        for label in sorted(mapping):
            v = mapping[label]
            cell = load_cell(rdir, cutoff, v)
            if "error" in cell:
                print(f"  {label}={v:9s} FAILED: {cell['error']}")
                continue
            s = score_digest(cell["digest"]["items"], engaged)
            human = ratings.get(cutoff, {}).get(label)
            parts = [f"auto={s['auto']:.3f} (mrr {s['mrr']:.2f} cov {s['coverage']:.2f})"]
            if human:
                parts.append(f"you={human}/5")
                combined = round(0.5 * s["auto"] + 0.5 * (human / 5), 3)
            else:
                combined = s["auto"]
            parts.append(f"=> {combined:.3f}")
            print(f"  {label}={v:9s} " + " ".join(parts))
            totals[v] = totals.get(v, 0) + combined
            counts[v] = counts.get(v, 0) + 1
    print("\n=== overall ===")
    for v, tot in sorted(totals.items(), key=lambda kv: -kv[1] / counts[kv[0]]):
        print(f"  {v:9s} avg {tot/counts[v]:.3f} over {counts[v]} windows")


REAL_STORE = os.path.expanduser("~/Library/Application Support/Mosaic")


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    if argv[1] == "survey":
        return cmd_survey(argv[2:]) or 0
    if argv[1] == "run":
        # Outputs (done.json, focus.json) go to scratch; the message and
        # WhatsApp stores default to the REAL ones — imported by focus.py
        # at import time, so these must be set before its first import.
        os.environ.setdefault("STORE_DIR", "/tmp/focuslab")
        os.environ.setdefault("MESSAGES_DB_PATH", os.path.join(REAL_STORE, "messages.db"))
        os.environ.setdefault("WHATSAPP_DB_PATH", os.path.join(REAL_STORE, "whatsapp.db"))
        os.makedirs("/tmp/focuslab", exist_ok=True)
        return cmd_run(argv[2:]) or 0
    if argv[1] == "rate":
        return cmd_rate(argv[2:]) or 0
    if argv[1] == "score":
        return cmd_score(argv[2:]) or 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
