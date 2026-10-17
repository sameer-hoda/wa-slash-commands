import os
import sqlite3
import sys
from pathlib import Path

os.environ["GEMINI_API_KEY"] = ""
os.environ["OWNER_PHONE_NUMBER"] = ""
os.environ["MECHAT_JID"] = ""

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


def build_session_db(path, phone, lid="", lid_map=None):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE whatsmeow_device (jid TEXT, lid TEXT)")
    con.execute("CREATE TABLE whatsmeow_lid_map (lid TEXT, pn TEXT)")
    if phone:
        con.execute(
            "INSERT INTO whatsmeow_device (jid, lid) VALUES (?, ?)",
            (f"{phone}:16@s.whatsapp.net", f"{lid}:37@lid" if lid else ""),
        )
    for l, p in lid_map or []:
        con.execute("INSERT INTO whatsmeow_lid_map (lid, pn) VALUES (?, ?)", (l, p))
    con.commit()
    con.close()


def build_messages_db(path, chats):
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE chats (jid TEXT PRIMARY KEY, name TEXT, last_message_time TIMESTAMP)"
    )
    con.execute(
        """CREATE TABLE messages (
            id TEXT, chat_jid TEXT, sender TEXT, content TEXT, timestamp TIMESTAMP,
            is_from_me BOOLEAN, media_type TEXT, filename TEXT, url TEXT,
            media_key BLOB, file_sha256 BLOB, file_enc_sha256 BLOB, file_length INTEGER,
            PRIMARY KEY (id, chat_jid)
        )"""
    )
    for jid, name, rows in chats:
        last = max(ts for ts, *_ in rows) if rows else "2026-01-01 00:00:00"
        con.execute("INSERT INTO chats VALUES (?, ?, ?)", (jid, name, last))
        for i, (ts, from_me, content) in enumerate(rows):
            con.execute(
                "INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (f"{jid}-{i}", jid, "me" if from_me else "them", content, ts, from_me),
            )
    con.commit()
    con.close()


@pytest.fixture
def store(tmp_path, monkeypatch):
    d = tmp_path / "store"
    d.mkdir()
    monkeypatch.setenv("STORE_DIR", str(d))
    monkeypatch.setenv("WHATSAPP_DB_PATH", str(d / "whatsapp.db"))
    monkeypatch.setenv("MESSAGES_DB_PATH", str(d / "messages.db"))
    import mechat

    monkeypatch.setattr(mechat, "STORE_DIR", d)
    monkeypatch.setattr(mechat, "MECHAT_FILE", d / "mechat.json")
    monkeypatch.setattr(mechat, "BRIDGE_TOKEN_FILE", d / "bridge_token")
    return d
