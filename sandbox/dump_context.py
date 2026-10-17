#!/usr/bin/env python3
"""Dump a read-only context fixture for the /pending sandbox.

    python3 sandbox/dump_context.py --chat "<group name substring>"

Writes sandbox/data/context.json with three message windows (24h / 7d / 30d),
sender names resolved exactly like the live engine, timestamps in UTC (IST is
applied at format time). The live databases are opened read-only.
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
ROOT = SANDBOX.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SANDBOX))

import sqlite3  # noqa: E402

import engine  # noqa: E402

WINDOWS = {"24h": (1, 2000), "7d": (7, 1000), "30d": (30, 500)}


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


def dump(chat_part: str, out_path: Path) -> dict:
    jid, name = find_chat(chat_part)
    ctx = {
        "meta": {
            "chat_jid": jid,
            "chat_name": name,
            "dumped_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "source": engine.MESSAGES_DB_PATH,
        },
        "windows": {},
    }
    for label, (days, limit) in WINDOWS.items():
        msgs = engine.get_messages(jid, days=days, limit=limit)
        ctx["windows"][label] = {
            "days": days,
            "limit": limit,
            "count": len(msgs),
            "messages": [
                {
                    "ts": dt.isoformat() if dt else None,
                    "sender": sender,
                    "content": content,
                }
                for sender, content, dt in msgs
            ],
        }
    meta = sqlite3.connect(f"file:{engine.MESSAGES_DB_PATH}?mode=ro", uri=True)
    try:
        row = meta.execute(
            "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM messages "
            "WHERE chat_jid = ? AND content IS NOT NULL AND TRIM(content) != ''",
            (jid,),
        ).fetchone()
    finally:
        meta.close()
    ctx["meta"].update({"total_msgs": row[0], "first_ts": row[1], "last_ts": row[2]})
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
    for label, w in ctx["windows"].items():
        print(f"   window {label}: {w['count']} msgs (limit {w['limit']})")
    print(f"   → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
