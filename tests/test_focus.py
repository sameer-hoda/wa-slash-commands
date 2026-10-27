"""Tests for focus.py — hourly Top-10 pipeline.

Uses throwaway SQLite fixtures (never the user's real databases):
STORE_DIR/MESSAGES_DB_PATH/WHATSAPP_DB_PATH point at tmp_path.
"""
import datetime
import importlib
import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def focusmod(tmp_path, monkeypatch):
    monkeypatch.setenv("STORE_DIR", str(tmp_path))
    monkeypatch.setenv("MESSAGES_DB_PATH", str(tmp_path / "messages.db"))
    monkeypatch.setenv("WHATSAPP_DB_PATH", str(tmp_path / "whatsapp.db"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    if "focus" in sys.modules:
        del sys.modules["focus"]
    import focus as f
    return importlib.reload(f)


def make_dbs(path, chats, archived=()):
    """chats: {jid: [(sender, text, is_from_me, hours_ago), ...]}."""
    now = datetime.datetime.now(datetime.timezone.utc)
    mdb = sqlite3.connect(path / "messages.db")
    mdb.execute("CREATE TABLE chats (jid TEXT PRIMARY KEY, name TEXT, last_message_time TIMESTAMP)")
    mdb.execute("""CREATE TABLE messages (id TEXT, chat_jid TEXT, sender TEXT, content TEXT,
                   timestamp TIMESTAMP, is_from_me BOOLEAN, media_type TEXT, filename TEXT,
                   url TEXT, media_key BLOB, file_sha256 BLOB, file_enc_sha256 BLOB, file_length INTEGER,
                   PRIMARY KEY (id, chat_jid))""")
    wdb = sqlite3.connect(path / "whatsapp.db")
    wdb.execute("CREATE TABLE whatsmeow_chat_settings (our_jid TEXT, chat_jid TEXT, muted_until BIGINT NOT NULL DEFAULT 0, pinned BOOLEAN NOT NULL DEFAULT false, archived BOOLEAN NOT NULL DEFAULT false, wasa_root_secret_id TEXT NOT NULL DEFAULT '', PRIMARY KEY (our_jid, chat_jid))")
    n = 0
    for jid, msgs in chats.items():
        last = ""
        for sender, text, me, ago in msgs:
            n += 1
            ts = (now - datetime.timedelta(hours=ago)).isoformat()
            mdb.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (f"m{n}", jid, sender, text, ts, me, "", "", "", None, None, None, 0))
            if not last or ts > last:
                last = ts
        mdb.execute("INSERT INTO chats VALUES (?,?,?)", (jid, jid.split("@")[0], last))
        wdb.execute("INSERT INTO whatsmeow_chat_settings VALUES (?,?,?,?,?,?)",
                    ("me", jid, 0, False, jid in archived, ""))
    mdb.commit(); wdb.commit(); mdb.close(); wdb.close()


def test_archived_chats_excluded(focusmod, tmp_path):
    make_dbs(tmp_path, {
        "a@g.us": [("x", "hello", False, 1)],
        "b@g.us": [("y", "hello", False, 1)],
    }, archived={"b@g.us"})
    chats = focusmod.recent_chats(datetime.datetime.now(datetime.timezone.utc))
    assert "a@g.us" in chats and "b@g.us" not in chats


def test_window_cutoff(focusmod, tmp_path):
    make_dbs(tmp_path, {
        "old@g.us": [("x", "hello", False, 60)],
        "new@g.us": [("y", "hello", False, 1)],
    })
    chats = focusmod.recent_chats(datetime.datetime.now(datetime.timezone.utc))
    assert set(chats) == {"new@g.us"}


def test_user_messages_weighted(focusmod, tmp_path):
    make_dbs(tmp_path, {
        "quiet@g.us": [("x", "status update", False, 1)],
        "mine@g.us": [("x", "can you send it?", False, 1),
                      ("me", "yes, I will send it tonight", True, 0.9)],
    })
    now = datetime.datetime.now(datetime.timezone.utc)
    chats = focusmod.recent_chats(now)
    assert focusmod.chat_score(chats["mine@g.us"], now, set()) > \
        focusmod.chat_score(chats["quiet@g.us"], now, set())


def test_stable_id(focusmod):
    assert focusmod.stable_id("a@g.us", "Send  the  deck") == \
        focusmod.stable_id("a@g.us", "send the deck")
    assert focusmod.stable_id("a@g.us", "Send the deck") != \
        focusmod.stable_id("b@g.us", "Send the deck")


def test_done_suppress_and_resurface(focusmod, tmp_path):
    now = datetime.datetime.now(datetime.timezone.utc)
    chats = {"g@g.us": {"name": "G", "msgs": [{"me": False}], "last_ts": (now - datetime.timedelta(hours=1)).isoformat()}}
    focusmod.mark_done("abc123", title="Old task", chat_jid="g@g.us",
                       last_activity=(now - datetime.timedelta(hours=5)).isoformat())
    done = focusmod.load_done()
    assert "abc123" in done
    # Pretend the task was marked done 5h ago (mark_done stamps now).
    done["abc123"]["done_at"] = (now - datetime.timedelta(hours=5)).isoformat()
    focusmod.save_done(done)
    done = focusmod.load_done()
    # Newer chat activity -> reopened candidate.
    notes = focusmod.reopened_notes(["g@g.us"], chats, done)
    assert len(notes) == 1 and "Old task" in notes[0]
    # Stale activity -> stays buried.
    chats["g@g.us"]["last_ts"] = (now - datetime.timedelta(hours=6)).isoformat()
    assert focusmod.reopened_notes(["g@g.us"], chats, done) == []


def test_upper_bound_no_leakage(focusmod, tmp_path):
    # Production timestamps use a SPACE separator; ISO bounds use "T".
    # A same-calendar-day message AFTER the cutoff must not leak in.
    con = sqlite3.connect(tmp_path / "messages.db")
    con.execute("CREATE TABLE chats (jid TEXT PRIMARY KEY, name TEXT, last_message_time TIMESTAMP)")
    con.execute("""CREATE TABLE messages (id TEXT, chat_jid TEXT, sender TEXT, content TEXT,
                   timestamp TIMESTAMP, is_from_me BOOLEAN, media_type TEXT, filename TEXT,
                   url TEXT, media_key BLOB, file_sha256 BLOB, file_enc_sha256 BLOB, file_length INTEGER,
                   PRIMARY KEY (id, chat_jid))""")
    con.execute("INSERT INTO chats VALUES (?,?,?)", ("g@g.us", "g", "2026-10-27 12:00:00+05:30"))
    con.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("m1", "g@g.us", "x", "before cutoff", "2026-10-27 04:00:00+05:30", False, "", "", "", None, None, None, 0))
    con.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("m2", "g@g.us", "x", "after cutoff same day", "2026-10-27 12:00:00+05:30", False, "", "", "", None, None, None, 0))
    con.commit(); con.close()
    wdb = sqlite3.connect(tmp_path / "whatsapp.db")
    wdb.execute("CREATE TABLE whatsmeow_chat_settings (our_jid TEXT, chat_jid TEXT, muted_until BIGINT NOT NULL DEFAULT 0, pinned BOOLEAN NOT NULL DEFAULT false, archived BOOLEAN NOT NULL DEFAULT false, wasa_root_secret_id TEXT NOT NULL DEFAULT '', PRIMARY KEY (our_jid, chat_jid))")
    wdb.commit(); wdb.close()
    now = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=datetime.timezone.utc)
    chats = focusmod.recent_chats(now, upper="2026-10-27T10:00:00+05:30")
    assert set(chats) == {"g@g.us"}
    assert [m["text"] for m in chats["g@g.us"]["msgs"]] == ["before cutoff"]


def test_stale_chat_row_does_not_hide_chat(focusmod, tmp_path):
    """Regression: chats.last_message_time goes stale on backfilled history.
    Candidate chats must come from messages, never from that column."""
    con = sqlite3.connect(tmp_path / "messages.db")
    con.execute("CREATE TABLE chats (jid TEXT PRIMARY KEY, name TEXT, last_message_time TIMESTAMP)")
    con.execute("""CREATE TABLE messages (id TEXT, chat_jid TEXT, sender TEXT, content TEXT,
                   timestamp TIMESTAMP, is_from_me BOOLEAN, media_type TEXT, filename TEXT,
                   url TEXT, media_key BLOB, file_sha256 BLOB, file_enc_sha256 BLOB, file_length INTEGER,
                   PRIMARY KEY (id, chat_jid))""")
    con.execute("INSERT INTO chats VALUES (?,?,?)", ("g@g.us", "G", "2026-01-01 00:00:00+05:30"))
    con.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("m1", "g@g.us", "x", "fresh hello", "2026-10-27 04:00:00+05:30", False, "", "", "", None, None, None, 0))
    con.commit(); con.close()
    wdb = sqlite3.connect(tmp_path / "whatsapp.db")
    wdb.execute("CREATE TABLE whatsmeow_chat_settings (our_jid TEXT, chat_jid TEXT, muted_until BIGINT NOT NULL DEFAULT 0, pinned BOOLEAN NOT NULL DEFAULT false, archived BOOLEAN NOT NULL DEFAULT false, wasa_root_secret_id TEXT NOT NULL DEFAULT '', PRIMARY KEY (our_jid, chat_jid))")
    wdb.commit(); wdb.close()
    now = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=datetime.timezone.utc)
    chats = focusmod.recent_chats(now)
    assert set(chats) == {"g@g.us"}
    assert chats["g@g.us"]["name"] == "G"


def test_contract_accepts_sample(focusmod):
    with open(os.path.join(os.path.dirname(__file__), "..", "mac", "tools", "top10.sample.json")) as f:
        assert focusmod.validate_digest(json.load(f))[0]


def test_contract_rejects_bad(focusmod):
    with open(os.path.join(os.path.dirname(__file__), "..", "mac", "tools", "top10.sample.json")) as f:
        good = json.load(f)
    bad_source = json.loads(json.dumps(good))
    bad_source["items"][0]["source"] = "banter"
    assert not focusmod.validate_digest(bad_source)[0]
    too_many = json.loads(json.dumps(good))
    too_many["items"].append(dict(too_many["items"][0], id="zzz", rank=11))
    assert not focusmod.validate_digest(too_many)[0]
    dup_rank = json.loads(json.dumps(good))
    dup_rank["items"][1]["rank"] = 1
    assert not focusmod.validate_digest(dup_rank)[0]
    missing_jid = json.loads(json.dumps(good))
    del missing_jid["items"][0]["chat_jid"]
    assert not focusmod.validate_digest(missing_jid)[0]
    null_jid = json.loads(json.dumps(good))
    null_jid["items"][0]["chat_jid"] = None
    assert focusmod.validate_digest(null_jid)[0]


def test_due_laundering_nulled(focusmod, tmp_path, monkeypatch):
    import engine
    make_dbs(tmp_path, {"g@g.us": [("x", "send it tonight", False, 1)]})
    monkeypatch.setattr(engine, "gemini_json", lambda *a, **k: {
        "headline": "h", "items": [{
            "title": "Send the thing", "why": "You promised",
            "chat_name": "G", "chat_jid": "g@g.us", "source": "commitment",
            "urgency": "high", "waiting_on": "you",
            "due": "2026-10-27T18:00:00.000Z",
            "last_activity": "2026-10-27 23:30:00+05:30"}]})
    doc, _ = focusmod.rank_once()
    assert doc["items"][0]["due"] is None


def test_genuine_due_kept(focusmod, tmp_path, monkeypatch):
    import engine
    make_dbs(tmp_path, {"g@g.us": [("x", "send it tonight", False, 1)]})
    monkeypatch.setattr(engine, "gemini_json", lambda *a, **k: {
        "headline": "h", "items": [{
            "title": "Send the thing", "why": "You promised",
            "chat_name": "G", "chat_jid": "g@g.us", "source": "commitment",
            "urgency": "high", "waiting_on": "you",
            "due": "2026-10-28T18:00:00+05:30",
            "last_activity": "2026-10-27 23:30:00+05:30"}]})
    doc, _ = focusmod.rank_once()
    assert doc["items"][0]["due"] == "2026-10-28T18:00:00+05:30"


def test_rank_once_end_to_end(focusmod, tmp_path, monkeypatch):
    """Full pass with a stubbed LLM: gather -> prompt -> validate -> write."""
    make_dbs(tmp_path, {
        "me@s.whatsapp.net": [("me", "remind me to send the deck", True, 1)],
        "g@g.us": [("x", "can you send the figures tonight?", False, 2),
                   ("me", "yes, I will send them tonight", True, 1)],
    })
    import engine
    calls = {}

    def fake_gemini(prompt, fallback, schema=None):
        calls["prompt"] = prompt
        assert schema is not None
        return {"headline": "Launch is gated on the deck.",
                "items": [
                    {"title": "Send Acme the figures", "why": "You promised them tonight.",
                     "chat_name": "G", "chat_jid": "g@g.us", "source": "commitment",
                     "urgency": "high", "waiting_on": "you",
                     "last_activity": "2026-10-27T18:00:00+05:30"}]}
    monkeypatch.setattr(engine, "gemini_json", fake_gemini)
    doc, tracker = focusmod.rank_once()
    assert doc["items"][0]["rank"] == 1
    assert len(doc["items"][0]["id"]) == 12
    assert tracker.records and tracker.records[0].model == focusmod.MODEL
    on_disk = json.load(open(tmp_path / "focus.json"))
    assert on_disk == doc
    assert focusmod.validate_digest(on_disk)[0]
    # Done-memory honored: after marking done, the item must not regenerate.
    focusmod.mark_done(doc["items"][0]["id"], title="Send Acme the figures",
                       chat_jid="g@g.us", last_activity="2026-10-27T18:00:00+05:30")
    assert focusmod.reopened_notes(["g@g.us"], {"g@g.us": {"last_ts": "2026-10-26T00:00:00+05:30"}}, focusmod.load_done()) == []


def test_rank_failure_writes_reason(focusmod, tmp_path, monkeypatch):
    import engine
    monkeypatch.setattr(engine, "gemini_json", lambda *a, **k: {"_gemini_failed": True})
    make_dbs(tmp_path, {"g@g.us": [("x", "hello", False, 1)]})
    assert focusmod.main(["focus.py", "--rank"]) == 1
    err = json.load(open(tmp_path / "focus_error.json"))
    assert err["reason"] == "gemini"


def test_canon_jid_exact_and_variants(focusmod):
    picks = ["123@lid", "120@g.us", "456@s.whatsapp.net"]
    assert focusmod.canon_jid("123@lid", picks) == "123@lid"
    assert focusmod.canon_jid("123", picks) == "123@lid"
    assert focusmod.canon_jid("123@s.whatsapp.net", picks) == "123@lid"
    assert focusmod.canon_jid("120@g.us", picks) == "120@g.us"
    assert focusmod.canon_jid("120", picks) is None  # groups need exact
    assert focusmod.canon_jid("", picks) is None
    assert focusmod.canon_jid("999@lid", picks) is None
    # Ambiguous digit collision across two picks -> None, never a wrong link.
    assert focusmod.canon_jid("456", ["456@lid", "456@s.whatsapp.net"]) is None


def test_forget_on_undo(focusmod):
    focusmod.mark_done("x1", title="T", chat_jid="g@g.us")
    assert "x1" in focusmod.load_done()
    focusmod.mark_done("forget:x1")
    assert "x1" not in focusmod.load_done()


def test_cost_tracker_budget(focusmod):
    t = focusmod.CostTracker(budget_limit=0.000001)
    rec = focusmod.estimate_cost("m", "x" * 4000, "y" * 4000)
    assert rec.in_chars == 4000 and rec.est_usd > 0
    assert t.add(rec).over_budget
    assert not focusmod.CostTracker().over_budget
