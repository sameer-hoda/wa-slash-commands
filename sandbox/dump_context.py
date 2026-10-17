#!/usr/bin/env python3
"""Dump a read-only context fixture for the Mosaic sandbox lab.

    python3 sandbox/dump_context.py --chat "<group name substring>"

Writes sandbox/data/context.json with four message windows
(24h / 7d / 14d / 30d). One dump serves every command sandbox (/pending,
/sotu, /recap, /stats, /eli5).

Sender names: if sandbox/data/sender_map.json exists (see
sandbox/recover_senders.py), it wins by message id — the live store lost its
per-message sender mapping in a mid-resync, and the map keeps real names in
the fixture. Otherwise the engine's normal lookup is used. Timestamps are
stored in UTC; IST is applied at format time. The live database is opened
read-only.
"""

import argparse
import datetime
import json
import os
import sqlite3
import sys
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
ROOT = SANDBOX.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SANDBOX))

import engine  # noqa: E402
from recover_senders import NAME_OVERRIDES  # noqa: E402

WINDOWS = {"24h": (1, 2000), "7d": (7, 1000), "14d": (14, 1000), "30d": (30, 500)}
SENDER_MAP_PATH = SANDBOX / "data" / "sender_map.json"


def find_chat(name_part: str) -> tuple[str, str]:
    con = sqlite3.connect(f"file:{engine.MESSAGES_DB_PATH}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT jid, name FROM chats WHERE lower(name) LIKE ? ORDER BY last_message_time DESC LIMIT 1",
            (f"%{name_part.lower()}%",),
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise SystemExit(f"no chat matching {name_part!r} in {engine.MESSAGES_DB_PATH}")
    return row[0], row[1] or row[0]


def _load_sender_map() -> dict:
    if SENDER_MAP_PATH.exists():
        try:
            return json.loads(SENDER_MAP_PATH.read_text())
        except Exception:
            return {}
    return {}


def _window_messages(con, jid: str, days: int, limit: int, sender_map: dict):
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    rows = con.execute(
        "SELECT id, sender, content, timestamp FROM messages "
        "WHERE chat_jid = ? AND timestamp > ? AND content IS NOT NULL AND TRIM(content) != '' "
        "ORDER BY timestamp DESC LIMIT ?",
        (jid, cutoff, limit),
    ).fetchall()
    out, mapped = [], 0
    for mid, sender, content, ts in reversed(rows):
        dt = engine.parse_ts(ts)
        name = sender_map.get(mid)
        if name:
            mapped += 1
        else:
            name = engine._resolve_sender_name(sender or "")
            name = NAME_OVERRIDES.get((sender or "").strip().lstrip("+"), name)
        out.append({
            "id": mid,
            "ts": dt.isoformat() if dt else None,
            "sender": name,
            "content": content,
        })
    return out, mapped


def dump(chat_part: str, out_path: Path) -> dict:
    jid, name = find_chat(chat_part)
    sender_map = _load_sender_map()
    con = sqlite3.connect(f"file:{engine.MESSAGES_DB_PATH}?mode=ro", uri=True)
    ctx = {
        "meta": {
            "chat_jid": jid,
            "chat_name": name,
            "dumped_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "source": engine.MESSAGES_DB_PATH,
            "sender_map": str(SENDER_MAP_PATH) if sender_map else "",
        },
        "windows": {},
    }
    total_mapped = total = 0
    try:
        for label, (days, limit) in WINDOWS.items():
            msgs, mapped = _window_messages(con, jid, days, limit, sender_map)
            total_mapped += mapped
            total += len(msgs)
            ctx["windows"][label] = {
                "days": days,
                "limit": limit,
                "count": len(msgs),
                "messages": msgs,
            }
        row = con.execute(
            "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM messages "
            "WHERE chat_jid = ? AND content IS NOT NULL AND TRIM(content) != ''",
            (jid,),
        ).fetchone()
    finally:
        con.close()
    ctx["meta"].update({"total_msgs": row[0], "first_ts": row[1], "last_ts": row[2],
                        "named_msgs": total_mapped})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ctx, ensure_ascii=False, indent=1))
    return ctx


def main() -> int:
    ap = argparse.ArgumentParser(description="Dump a chat context fixture for the sandbox")
    ap.add_argument("--chat", default=os.getenv("SANDBOX_CHAT", ""),
                    help="chat name (substring) — any group works")
    ap.add_argument("--out", default=str(SANDBOX / "data" / "context.json"))
    args = ap.parse_args()
    if not args.chat:
        raise SystemExit('pass a chat:  python3 sandbox/dump_context.py --chat "<group name>"')

    ctx = dump(args.chat, Path(args.out))
    m = ctx["meta"]
    print(f"✅ dumped: {m['chat_name']} ({m['chat_jid']})")
    print(f"   total: {m['total_msgs']} msgs · {m['first_ts']} → {m['last_ts']}")
    print(f"   named via sender_map: {m['named_msgs']} window messages")
    for label, w in ctx["windows"].items():
        print(f"   window {label}: {w['count']} msgs (limit {w['limit']})")
    print(f"   → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
