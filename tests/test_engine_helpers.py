import datetime

import engine


def test_parse_ts_honors_positive_offset():
    assert engine.parse_ts("2026-10-17 11:39:31+05:30") == datetime.datetime(2026, 10, 17, 6, 9, 31)


def test_parse_ts_ist_roundtrip_renders_real_time():
    dt = engine.parse_ts("2026-10-17 11:39:31+05:30")
    assert engine.utc_to_ist(dt) == datetime.datetime(2026, 10, 17, 11, 39, 31)


def test_parse_ts_negative_offset_with_fraction():
    assert engine.parse_ts("2026-10-17 01:39:31.5-05:00") == datetime.datetime(2026, 10, 17, 6, 39, 31)


def test_parse_ts_naive_and_z_forms_stay_utc():
    expected = datetime.datetime(2026, 10, 17, 6, 9, 31)
    assert engine.parse_ts("2026-10-17 06:09:31") == expected
    assert engine.parse_ts("2026-10-17T06:09:31Z") == expected
    assert engine.parse_ts("2026-10-17 06:09:31.123456") == expected


def test_parse_ts_int_epoch():
    assert engine.parse_ts(1792226592) == datetime.datetime.utcfromtimestamp(1792226592)


def test_resolve_sender_name_chats_fallback(tmp_path, monkeypatch):
    import sqlite3

    wa = tmp_path / "whatsapp.db"
    msgs = tmp_path / "messages.db"
    con = sqlite3.connect(wa)
    con.execute("CREATE TABLE whatsmeow_lid_map (lid TEXT, pn TEXT)")
    con.execute("INSERT INTO whatsmeow_lid_map VALUES ('123456789012', '919999000011')")
    con.execute("CREATE TABLE whatsmeow_contacts "
                "(their_jid TEXT, push_name TEXT, full_name TEXT, first_name TEXT, business_name TEXT)")
    con.commit()
    con.close()
    con = sqlite3.connect(msgs)
    con.execute("CREATE TABLE chats (jid TEXT PRIMARY KEY, name TEXT, last_message_time TEXT)")
    con.execute("INSERT INTO chats VALUES ('919999000011@s.whatsapp.net', 'Priya Sharma', '')")
    con.commit()
    con.close()

    monkeypatch.setattr(engine, "WHATSAPP_DB_PATH", str(wa))
    monkeypatch.setattr(engine, "MESSAGES_DB_PATH", str(msgs))

    assert engine._resolve_sender_name("123456789012") == "Priya Sharma"
