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
import sys
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
ROOT = SANDBOX.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SANDBOX))

JID_PAT = re.compile(rb"([0-9]{8,20})@(lid|s\.whatsapp\.net)")
MSG_PAT = re.compile(rb"[A-Z0-9]{18,26}")


def carve(db_path: Path, group_jid: str) -> dict:
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
        pairs[m2.group(0).decode()] = m.group(1).decode()
    return pairs


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
            cache[sender] = name if name and name != sender else sender
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
    resolved = resolve(pairs)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(resolved, indent=1, ensure_ascii=False))

    import collections

    names = collections.Counter(resolved.values())
    print(f"✅ carved {len(pairs)} messages · {len(names)} senders")
    for name, n in names.most_common(15):
        print(f"   {n:>5}  {name}")
    print(f"   → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
