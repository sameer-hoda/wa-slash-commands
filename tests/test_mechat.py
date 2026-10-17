import json

import mechat
from conftest import build_messages_db, build_session_db

PHONE = "919876543210"
LID = "219541632213229"
PN_JID = f"{PHONE}@s.whatsapp.net"
LID_JID = f"{LID}@lid"


def _fixtures(store, messages=None, session=True, lid=LID, lid_map=None, env_phone=None,
              monkeypatch=None):
    if session:
        build_session_db(store / "whatsapp.db", PHONE, lid, lid_map)
    if env_phone is not None:
        monkeypatch.setenv("OWNER_PHONE_NUMBER", env_phone)
    build_messages_db(store / "messages.db", messages or [])


def test_resolve_pn_only(store, monkeypatch):
    _fixtures(store, messages=[(PN_JID, "Me (You)", [("2026-10-17 09:00:00", 1, "note")])],
              monkeypatch=monkeypatch)
    jid, how = mechat.resolve_self_chat()
    assert jid == PN_JID
    assert how == "messages:session-db"
    assert mechat.verify_mechat(jid)


def test_resolve_lid_freshest_wins(store, monkeypatch):
    _fixtures(store, messages=[
        (PN_JID, "Me (You)", [("2026-10-10 09:00:00", 1, "old")]),
        (LID_JID, "Me (You)", [("2026-10-17 09:00:00", 1, "new")]),
    ], monkeypatch=monkeypatch)
    jid, how = mechat.resolve_self_chat()
    assert jid == LID_JID
    assert how == "messages:session-db"
    assert mechat.verify_mechat(jid)


def test_resolve_definitional_pn_without_messages(store, monkeypatch):
    _fixtures(store, messages=[], monkeypatch=monkeypatch)
    jid, how = mechat.resolve_self_chat()
    assert jid == PN_JID
    assert how == "definitional-pn:session-db"
    assert mechat.verify_mechat(jid)


def test_resolve_from_env_when_no_session(store, monkeypatch):
    _fixtures(store, session=False, env_phone=f"+{PHONE}",
              messages=[(PN_JID, "Me (You)", [("2026-10-17 09:00:00", 1, "note")])],
              monkeypatch=monkeypatch)
    jid, how = mechat.resolve_self_chat()
    assert jid == PN_JID
    assert how == "messages:env"


def test_resolve_fails_loud_when_nothing(store, monkeypatch):
    _fixtures(store, session=False, monkeypatch=monkeypatch)
    jid, how = mechat.resolve_self_chat()
    assert jid is None and how == "not-found"
    assert mechat.get_mechat_jid() == ""
    result = mechat.resolve_and_persist()
    assert result["ok"] is False
    assert mechat.main(["--resolve"]) == 2


def test_mechat_jid_env_wins_when_valid(store, monkeypatch):
    _fixtures(store, monkeypatch=monkeypatch)
    monkeypatch.setenv("MECHAT_JID", PN_JID)
    jid, how = mechat.resolve_self_chat()
    assert jid == PN_JID and how == "config"


def test_mechat_jid_env_invalid_fails_loud(store, monkeypatch):
    _fixtures(store, monkeypatch=monkeypatch)
    monkeypatch.setenv("MECHAT_JID", f"{PHONE}@g.us")
    jid, how = mechat.resolve_self_chat()
    assert jid is None and how == "config-invalid"
    assert mechat.resolve_and_persist()["ok"] is False
    assert mechat.get_mechat_jid() == ""


def test_is_owner_jid_pn_lid_and_rejects_others(store, monkeypatch):
    _fixtures(store, monkeypatch=monkeypatch)
    assert mechat.is_owner_jid(PN_JID)
    assert mechat.is_owner_jid(LID_JID)
    assert mechat.is_owner_jid(f"{PHONE}:86@s.whatsapp.net")
    assert not mechat.is_owner_jid("919999999999@s.whatsapp.net")
    assert not mechat.is_owner_jid(f"{PHONE}@g.us")
    assert not mechat.is_owner_jid("status@broadcast")
    assert not mechat.is_owner_jid("")


def test_is_owner_jid_via_lid_map(store, monkeypatch):
    build_session_db(store / "whatsapp.db", None, lid_map=[(LID, PHONE)])
    monkeypatch.setenv("OWNER_PHONE_NUMBER", PHONE)
    build_messages_db(store / "messages.db", [])
    assert mechat.is_owner_jid(LID_JID)


def test_persist_and_get_mechat_jid(store, monkeypatch):
    _fixtures(store, messages=[(PN_JID, "Me (You)", [("2026-10-17 09:00:00", 1, "x")])],
              monkeypatch=monkeypatch)
    result = mechat.resolve_and_persist()
    assert result["ok"] and result["jid"] == PN_JID
    persisted = json.loads((store / "mechat.json").read_text())
    assert persisted["jid"] == PN_JID and persisted["welcomed"] is False
    assert mechat.get_mechat_jid() == PN_JID


def test_get_mechat_jid_reresolves_stale_persisted(store, monkeypatch):
    _fixtures(store, messages=[(LID_JID, "Me (You)", [("2026-10-17 09:00:00", 1, "x")])],
              monkeypatch=monkeypatch)
    mechat.persist("919111111111@s.whatsapp.net", "stale", PHONE)
    assert mechat.get_mechat_jid() == LID_JID


def test_verify_mechat_refuses_group_and_others(store, monkeypatch):
    _fixtures(store, monkeypatch=monkeypatch)
    assert not mechat.verify_mechat(f"{PHONE}@g.us")
    assert not mechat.verify_mechat("status@broadcast")
    assert not mechat.verify_mechat("919999999999@s.whatsapp.net")
    assert mechat.verify_mechat(PN_JID)


def test_welcome_once_sends_only_to_mechat(store, monkeypatch):
    _fixtures(store, messages=[(PN_JID, "Me (You)", [("2026-10-17 09:00:00", 1, "x")])],
              monkeypatch=monkeypatch)
    sent = []
    monkeypatch.setattr(mechat, "_send_via_bridge",
                        lambda jid, text: sent.append((jid, text)) or True)
    assert mechat.welcome_once() == "welcomed"
    assert len(sent) == 1 and sent[0][0] == PN_JID
    assert "Mosaic is connected" in sent[0][1]
    assert mechat.welcome_once() == "already-welcomed"
    assert len(sent) == 1


def test_welcome_once_without_mechat_never_sends(store, monkeypatch):
    _fixtures(store, session=False, monkeypatch=monkeypatch)
    sent = []
    monkeypatch.setattr(mechat, "_send_via_bridge",
                        lambda jid, text: sent.append((jid, text)) or True)
    assert mechat.welcome_once() == "no-mechat"
    assert sent == []
