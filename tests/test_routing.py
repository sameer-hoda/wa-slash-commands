import datetime
import json

import engine
import mechat
import wacmd
from conftest import build_messages_db, build_session_db

PHONE = "919876543210"
LID = "219541632213229"
PN_JID = f"{PHONE}@s.whatsapp.net"
LID_JID = f"{LID}@lid"
GROUP_JID = "120363001122334455@g.us"
OTHER = "919999999999@s.whatsapp.net"


def _owner_world(store, self_rows=None):
    build_session_db(store / "whatsapp.db", PHONE, LID, lid_map=[(LID, PHONE)])
    build_messages_db(store / "messages.db", [
        (PN_JID, "Me (You)",
         self_rows or [("2026-10-17 09:00:00", 1, "note")]),
    ])


def _wire_engine(monkeypatch, messages, sotu=None):
    monkeypatch.setattr(engine, "ai_available", lambda: True)
    monkeypatch.setattr(wacmd, "cache_read", lambda jid, cmd: None)
    monkeypatch.setattr(wacmd, "cache_write", lambda *a, **k: None)
    monkeypatch.setattr(wacmd, "get_messages",
                        lambda jid, days=30, limit=500: messages)
    monkeypatch.setattr(wacmd, "gemini_json",
                        lambda prompt, fallback, schema=None: sotu or fallback)


def _capture(monkeypatch):
    posts, deletes = [], []

    class R:
        status_code = 200
        text = ""

    def fake_post(url, json=None, headers=None, timeout=None):
        posts.append({"url": url, "json": json, "headers": headers or {}})
        return R()

    def fake_delete(*a, **k):
        deletes.append((a, k))
        return R()

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.delete", fake_delete)
    monkeypatch.delenv("BRIDGE_TOKEN", raising=False)
    return posts, deletes


def test_owner_sotu_in_group_answers_only_to_mechat(store, monkeypatch):
    _owner_world(store)
    fixture = {
        "group_purpose": "Acme launch", "big_picture_objective": "Ship v1",
        "key_themes": [{"title": "Landing", "description": "Design approved"}],
        "recent_happenings": "Launch moved to 22 Oct",
        "key_ask": "Priya needs the signed SOW",
    }
    _wire_engine(monkeypatch,
                 [("Priya", "can you sign the SOW?",
                   datetime.datetime(2026, 10, 16, 9, 0))],
                 sotu=fixture)
    posts, deletes = _capture(monkeypatch)

    wacmd.handle_command(GROUP_JID, PN_JID, "/sotu")

    assert len(posts) == 1
    assert posts[0]["json"]["recipient"] == PN_JID
    assert "State of the Union" in posts[0]["json"]["message"]
    assert GROUP_JID not in json.dumps(posts[0])
    assert deletes == []


def test_non_owner_command_is_silently_ignored(store, monkeypatch):
    _owner_world(store)
    _wire_engine(monkeypatch, [])
    posts, deletes = _capture(monkeypatch)

    wacmd.handle_command(GROUP_JID, OTHER, "/sotu")

    assert posts == [] and deletes == []


def test_owner_lid_form_is_accepted(store, monkeypatch):
    _owner_world(store)
    _wire_engine(monkeypatch, [])
    posts, deletes = _capture(monkeypatch)

    wacmd.handle_command(GROUP_JID, LID_JID, "/help")

    assert len(posts) == 1
    assert posts[0]["json"]["recipient"] == PN_JID
    assert "Available Commands" in posts[0]["json"]["message"]
    assert deletes == []


def test_mechat_lid_selfchat_resolves_to_pn_before_send(store, monkeypatch):
    build_session_db(store / "whatsapp.db", PHONE, LID, lid_map=[(LID, PHONE)])
    build_messages_db(store / "messages.db", [
        (LID_JID, "Me (You)", [("2026-10-17 09:00:00", 1, "note")]),
    ])
    _wire_engine(monkeypatch, [])
    posts, deletes = _capture(monkeypatch)
    import engine

    monkeypatch.setattr(engine, "WHATSAPP_DB_PATH", str(store / "whatsapp.db"))

    wacmd.handle_command(GROUP_JID, PN_JID, "/help")

    assert len(posts) == 1
    assert posts[0]["json"]["recipient"] == PN_JID
    assert deletes == []


def test_unresolved_mechat_drops_answer(store, monkeypatch):
    _wire_engine(monkeypatch, [])
    posts, deletes = _capture(monkeypatch)
    monkeypatch.setattr(mechat, "get_mechat_jid", lambda: "")
    monkeypatch.setattr(mechat, "is_owner_jid", lambda jid, session_db=None: True)

    wacmd.handle_command(GROUP_JID, PN_JID, "/help")
    wacmd.send_answer("hello")

    assert posts == [] and deletes == []


def test_send_message_carries_bridge_token(store, monkeypatch):
    (store / "bridge_token").write_text("t0k3n")
    posts, _deletes = _capture(monkeypatch)

    wacmd.send_message(PN_JID, "hi")

    assert posts[0]["headers"]["X-Bridge-Token"] == "t0k3n"


def test_missing_key_is_loud_not_fake_empty(store, monkeypatch):
    _owner_world(store)
    _wire_engine(monkeypatch, [])
    monkeypatch.setattr(engine, "ai_available", lambda: False)
    posts, deletes = _capture(monkeypatch)

    wacmd.handle_command(GROUP_JID, PN_JID, "/pending")

    assert len(posts) == 1
    assert "key is missing" in posts[0]["json"]["message"]
    assert "No critical open loops" not in posts[0]["json"]["message"]
    assert deletes == []


def test_help_still_works_without_key(store, monkeypatch):
    _owner_world(store)
    _wire_engine(monkeypatch, [])
    monkeypatch.setattr(engine, "ai_available", lambda: False)
    posts, _deletes = _capture(monkeypatch)

    wacmd.handle_command(GROUP_JID, PN_JID, "/help")

    assert len(posts) == 1
    assert "Available Commands" in posts[0]["json"]["message"]


def test_gemini_failure_is_not_faked_empty(store, monkeypatch):
    _owner_world(store)
    _wire_engine(monkeypatch, [("A", "hi",
                                datetime.datetime(2026, 10, 17, 9, 0))])
    monkeypatch.setattr(
        wacmd, "gemini_json",
        lambda prompt, fallback, schema=None: {**fallback, "_gemini_failed": True})
    writes = []
    monkeypatch.setattr(wacmd, "cache_write", lambda *a, **k: writes.append(a))
    posts, _deletes = _capture(monkeypatch)

    wacmd.handle_command(GROUP_JID, PN_JID, "/pending")

    assert len(posts) == 1
    assert "Analysis failed" in posts[0]["json"]["message"]
    assert "No critical open loops" not in posts[0]["json"]["message"]
    assert writes == []
