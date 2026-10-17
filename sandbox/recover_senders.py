#!/usr/bin/env python3
"""Recover per-message sender names from whatsapp.db free pages.

Why: a whatsmeow re-sync wiped whatsmeow_message_secrets (sender_jid per
message). The deleted rows are still carved-able from the SQLite file's free
pages — the table's text columns sit contiguously in each record, so we scan
raw bytes for `<group jid><sender jid><message id>` triples, then resolve each
sender id to a display name with the engine's normal lookup (lid_map →
contacts → chats fallback).

    python3 sandbox/recover_senders.py                 # writes sandbox/data/sender_map.json
    python3 sandbox/recover_senders.py --group 1203…@g.us --db store/whatsapp.db

The map is read by sandbox/dump_context.py so re-dumps keep real names even
while the live store is mid-resync. It lives in sandbox/data/ (gitignored).
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
ROOT = SANDBOX.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SANDBOX))

JID_PAT = re.compile(rb"([0-9]{8,20})@(lid|s\.whatsapp\.net)")
MSG_PAT = re.compile(rb"[A-Z0-9]{18,32}")

# The owner's phone (and its LID) resolves to the chats handle "@sameerhoda";
# use the real display name the old fixture had. 217935448666167 has no
# lid_map row; the old fixture's "Vignesh Chavan CRED" matched its counts.
NAME_OVERRIDES = {
    "919967151186": "Sameer Hoda",
    "219541632213229": "Sameer Hoda",
    "217935448666167": "Vignesh Chavan CRED",
}


def carve(db_path: Path, group_jid: str) -> dict:
    """Pass 1 — whatsapp.db message_secrets layout: group_jid, sender_jid, id."""
    data = db_path.read_bytes()
    group = group_jid.encode()
    pairs = {}
    pos = 0
    while True:
        i = data.find(group, pos)
        if i < 0:
            break
        pos = i + 1
        tail = data[i + len(group): i + len(group) + 80]
        m = JID_PAT.match(tail)
        if not m:
            continue
        m2 = MSG_PAT.match(tail[m.end():])
        if not m2:
            continue
        mid = m2.group(0).decode()
        pairs[mid] = m.group(1).decode()
        if len(mid) > 22:  # key-bytes may bleed into the match; keep the 22-char form too
            pairs[mid[:22]] = m.group(1).decode()
    return pairs


def carve_messages_db(db_path: Path, group_jid: str, known: set) -> dict:
    """Pass 2 — messages.db layout: message id, group_jid, sender digits.

    Old message rows (pre-resync) stored the real sender; freed pages still
    hold them. Only senders already vouched for by pass 1 are accepted —
    raw page bytes bleed into neighbouring digits, so unknown ids are dropped.
    """
    data = db_path.read_bytes()
    group = group_jid.encode()
    pairs = {}
    pos = 0
    while True:
        i = data.find(group, pos)
        if i < 0:
            break
        pos = i + len(group)
        before = data[max(0, i - 40):i]
        m = re.search(rb"([A-Z0-9]{18,32})$", before)
        if not m:
            continue
        m2 = re.match(rb"(\d{10,15})", data[pos: pos + 15])
        if not m2:
            continue
        sender = m2.group(1).decode()
        if sender in known:
            mid = m.group(1).decode()
            pairs[mid] = sender
            if len(mid) > 22:
                pairs[mid[:22]] = sender
    return pairs


def carve_by_content(db_path: Path, group_jid: str, known: set, have: set,
                     min_len: int = 24) -> dict:
    """Pass 3 — anchor on message content: sender digits sit right before it."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT id, content FROM messages WHERE chat_jid = ? AND content IS NOT NULL",
            (group_jid,),
        ).fetchall()
    finally:
        con.close()
    data = db_path.read_bytes()
    out = {}
    for mid, content in rows:
        if mid in have or len((content or "").strip()) < min_len:
            continue
        needle = content.strip()[:80].encode()
        pos = data.find(needle)
        while pos >= 0:
            before = data[max(0, pos - 20):pos]
            m = re.search(rb"(\d{10,15})$", before)
            if m and m.group(1).decode() in known:
                out[mid] = m.group(1).decode()
                break
            pos = data.find(needle, pos + 1)
    return out


def resolve(pairs: dict) -> dict:
    import engine

    cache = {}
    out = {}
    for mid, sender in pairs.items():
        if sender not in cache:
            try:
                name = engine._resolve_sender_name(sender)
            except Exception:
                name = sender
            cache[sender] = NAME_OVERRIDES.get(sender) or (name if name and name != sender else sender)
        out[mid] = cache[sender]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Carve sender names from whatsapp.db free pages")
    ap.add_argument("--db", default=str(ROOT / "store" / "whatsapp.db"))
    ap.add_argument("--group", default="120363406206264262@g.us",
                    help="group JID to recover senders for")
    ap.add_argument("--out", default=str(SANDBOX / "data" / "sender_map.json"))
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        raise SystemExit(f"no db at {db}")
    pairs = carve(db, args.group)
    n1 = len(pairs)
    known = set(pairs.values())
    msg_db = ROOT / "store" / "messages.db"
    if msg_db.exists():
        for mid, sender in carve_messages_db(msg_db, args.group, known).items():
            pairs.setdefault(mid, sender)
        n2 = len(pairs)
        for mid, sender in carve_by_content(msg_db, args.group, known, set(pairs)).items():
            pairs.setdefault(mid, sender)
        n3 = len(pairs)
    resolved = resolve(pairs)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(resolved, indent=1, ensure_ascii=False))

    import collections

    names = collections.Counter(resolved.values())
    print(f"✅ carved {len(pairs)} messages ({n1} via secrets pages, "
          f"{n2 - n1} via messages pages, {n3 - n2} via content anchors) · {len(names)} senders")
    for name, n in names.most_common(15):
        print(f"   {n:>5}  {name}")
    print(f"   → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
