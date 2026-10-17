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
