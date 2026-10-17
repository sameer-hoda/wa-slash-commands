import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sandbox"))

import approaches  # noqa: E402


def _ctx(messages=None):
    msgs = messages or []
    return {
        "meta": {"chat_jid": "1@g.us", "chat_name": "t"},
        "windows": {"30d": {"messages": msgs}, "7d": {"messages": msgs}},
        "options": {"clean": False},
    }


def test_registry_integrity():
    names = [a["name"] for a in approaches.APPROACHES]
    assert len(names) == len(set(names))
    assert set(names) == {"digest6", "chrono", "twopass", "ledger"}
    for a in approaches.APPROACHES:
        assert a["desc"] and a["hypothesis"]
        assert "build" in a or "custom_run" in a


def test_is_bot_noise():
    assert approaches.is_bot_noise("/pending")
    assert approaches.is_bot_noise("🎯 Something\n📅 x")
    assert approaches.is_bot_noise("text ⏭ *Next:* blah")
    assert approaches.is_bot_noise("⚠️ *Mosaic* · Offline")
    assert not approaches.is_bot_noise("hey can you share the deck?")


def test_clean_filter_and_format():
    msgs = [
        {"ts": "2026-10-17T09:00:00", "sender": "Priya", "content": "please share the deck"},
        {"ts": "2026-10-17T09:01:00", "sender": "Me", "content": "/pending"},
        {"ts": "2026-10-17T09:02:00", "sender": "Bot", "content": "🎯 Old digest"},
    ]
    ctx = _ctx(msgs)
    assert "Priya" in approaches.formatted_window(ctx, "30d")
    ctx["options"]["clean"] = True
    formatted = approaches.formatted_window(ctx, "30d")
    assert "Priya" in formatted
    assert "/pending" not in formatted
    assert "🎯" not in formatted


def test_merge6_prompt_contract_removed():
    assert "merge6" not in approaches.BY_NAME
    assert "asis" not in approaches.BY_NAME
    assert "rules" not in approaches.BY_NAME


def test_initiative_stats():
    data = {"initiatives": [
        {"title": "a", "updates": ["u1", "u2"], "next_steps": "x"},
        {"title": "b", "updates": [], "next_steps": ""},
    ]}
    assert approaches.initiative_stats(data) == {
        "inits": 2, "upd_max": 2, "upd_total": 2, "next": 1}


def test_rules_approach_removed():
    assert "rules" not in {a["name"] for a in approaches.APPROACHES}


# ── ledger ────────────────────────────────────────────────────────────────────

import datetime  # noqa: E402

import ledger  # noqa: E402


def _ledger_ctx():
    return {
        "meta": {
            "chat_jid": "1@g.us", "chat_name": "t",
            "dumped_at": "2026-10-17T12:00:00",
        },
        "windows": {"7d": {"messages": [
            {"ts": "2026-10-15T06:30:00", "sender": "Nikhil Saxena",
             "content": "@247265746751488 push IDFC webview live today"},
            {"ts": "2026-10-15T07:00:00", "sender": "Yash", "content": "will check"},
            {"ts": "2026-10-16T05:00:00", "sender": "Nikhil Saxena",
             "content": "@247265746751488 IDFC still not live, chase again"},
            {"ts": "2026-10-16T06:00:00", "sender": "Me", "content": "/pending"},
            {"ts": "2026-10-16T06:01:00", "sender": "Bot",
             "content": "🎯 Old digest ⏭ *Next:* x"},
        ]}},
        "options": {"clean": False},
    }


def test_ledger_day_and_since_labels():
    now = datetime.datetime(2026, 10, 17, 12, 0, tzinfo=ledger.IST)
    today = datetime.datetime(2026, 10, 17, 9, 0, tzinfo=ledger.IST)
    yday = datetime.datetime(2026, 10, 16, 9, 0, tzinfo=ledger.IST)
    thu = datetime.datetime(2026, 10, 15, 9, 0, tzinfo=ledger.IST)
    assert ledger.day_label(today, now) == "today"
    assert ledger.day_label(yday, now) == "yesterday"
    assert ledger.day_label(thu, now) == "Thu"
    assert ledger.since_label(thu, now) == "since Thu"


def test_ledger_transcript_cleans_and_resolves_mentions(monkeypatch):
    monkeypatch.setattr(ledger, "real_mention_map",
                        lambda ids: {"247265746751488": "Yash"})
    index, transcript, people = ledger.build_transcript(_ledger_ctx())
    assert transcript.count("[1]") == 1
    assert "/pending" not in transcript
    assert "🎯" not in transcript
    assert "@Yash" in transcript
    assert "Yash" in people and "Nikhil Saxena" in people
    assert len(index) == 3


def test_ledger_unresolved_mention_becomes_someone(monkeypatch):
    monkeypatch.setattr(ledger, "real_mention_map", lambda ids: {})
    _index, transcript, _people = ledger.build_transcript(_ledger_ctx())
    assert "@someone" in transcript


def test_ledger_clean_loops_drops_hallucinations_and_done():
    dt1 = datetime.datetime(2026, 10, 15, 9, 0, tzinfo=ledger.IST)
    dt2 = datetime.datetime(2026, 10, 16, 9, 0, tzinfo=ledger.IST)
    index = {1: (dt1, "A", "x"), 2: (dt2, "B", "y")}
    data = {"loops": [
        {"task": "fake cite", "owner": "Yash", "asked_by": "Nikhil", "opened": 99,
         "last_touch": 99, "chases": 1, "status": "open", "due": ""},
        {"task": "finished", "owner": "Yash", "asked_by": "Nikhil", "opened": 1,
         "last_touch": 2, "chases": 1, "status": "done", "due": ""},
        {"task": "real open", "owner": "Tanveen", "asked_by": "Shashank", "opened": 1,
         "last_touch": 2, "chases": 2, "status": "open", "due": "by noon"},
    ]}
    out = ledger.clean_loops(data, index)
    assert len(out) == 1
    assert out[0]["task"] == "real open"
    assert out[0]["opened_dt"] == dt1


def test_ledger_render_groups_by_owner_and_computes_dates(monkeypatch):
    monkeypatch.setattr(ledger, "real_mention_map", lambda ids: {})
    ctx = _ledger_ctx()
    index, _transcript, _people = ledger.build_transcript(ctx)
    now = ledger._now(ctx)
    data = {
        "headline": "Yash is holding the IDFC webview — unblock first.",
        "loops": [
            {"task": "Push IDFC webview live", "owner": "Yash",
             "asked_by": "Nikhil Saxena", "opened": 1, "last_touch": 3,
             "chases": 2, "status": "no_reply", "due": "today"},
        ],
    }
    out = ledger.render_ledger(data, index, now, chat_name="Branding OKR",
                               own_names=set())
    assert "📌 *Pending — Branding OKR*" in out
    assert "> Yash is holding the IDFC webview" in out
    assert "*Yash* · 1" in out
    assert "- ⚠️ Push IDFC webview live" in out
    assert "_Nikhil · since Thu · chased 2× · no reply_" in out
    assert "more" not in out


def test_ledger_render_shows_all_loops_and_you_first(monkeypatch):
    monkeypatch.setattr(ledger, "real_mention_map", lambda ids: {})
    ctx = _ledger_ctx()
    _index, _transcript, _people = ledger.build_transcript(ctx)
    now = ledger._now(ctx)
    dt = datetime.datetime(2026, 10, 15, 9, 0, tzinfo=ledger.IST)
    index = {i: (dt, "Sender", f"m{i}") for i in range(1, 10)}
    loops = [
        {"task": f"item{i}", "owner": "Yash", "asked_by": "Nikhil Saxena",
         "opened": i + 1, "last_touch": i + 1, "chases": 1, "status": "open",
         "due": ""}
        for i in range(7)
    ] + [
        {"task": "chatgpt access", "owner": "Sameer Hoda",
         "asked_by": "Nikhil Saxena", "opened": 9, "last_touch": 9,
         "chases": 1, "status": "no_reply", "due": ""},
    ]
    out = ledger.render_ledger({"headline": "", "loops": loops},
                               index, now, own_names={"Sameer Hoda"})
    for i in range(7):
        assert f"item{i}" in out
    assert "more" not in out
    assert "*Yash* · 7" in out
    assert "*You* · 1" in out
    assert out.index("*You*") < out.index("*Yash*")


def test_ledger_due_label_weekday_resolution_and_expiry():
    opened = datetime.datetime(2026, 10, 15, 9, 0, tzinfo=ledger.IST)   # Thu
    sun = datetime.datetime(2026, 10, 18, 12, 0, tzinfo=ledger.IST)
    tue = datetime.datetime(2026, 10, 20, 12, 0, tzinfo=ledger.IST)
    assert ledger.due_label("Monday", opened, sun) == ("Mon", False)
    assert ledger.due_label("Monday", opened, tue) == ("overdue", True)
    assert ledger.due_label("urgent", opened, sun) == (None, False)
    assert ledger.due_label("asap", opened, sun) == (None, False)
    assert ledger.due_label("by 12 noon", opened, sun) == ("overdue", True)
    assert ledger.due_label("", opened, sun) == (None, False)


def test_ledger_clean_loops_merges_same_owner_same_brand():
    dt1 = datetime.datetime(2026, 10, 15, 9, 0, tzinfo=ledger.IST)
    dt2 = datetime.datetime(2026, 10, 16, 9, 0, tzinfo=ledger.IST)
    index = {1: (dt1, "A", "x"), 2: (dt2, "B", "y")}
    data = {"loops": [
        {"task": "Fix Dreame webview underdelivery", "owner": "Yash",
         "asked_by": "Nikhil", "opened": 1, "last_touch": 2, "chases": 2,
         "status": "open", "due": ""},
        {"task": "Own Dreame execution", "owner": "Yash",
         "asked_by": "Nikhil", "opened": 2, "last_touch": 2, "chases": 1,
         "status": "no_reply", "due": "Monday"},
    ]}
    out = ledger.clean_loops(data, index)
    assert len(out) == 1
    assert out[0]["chases"] == 2
    assert out[0]["status"] == "no_reply"
    assert out[0]["due"] == "Monday"


def test_ledger_candidate_asks_and_prompt(monkeypatch):
    monkeypatch.setattr(ledger, "real_mention_map",
                        lambda ids: {"247265746751488": "Yash"})
    ctx = _ledger_ctx()
    index, _transcript, _people = ledger.build_transcript(ctx)
    cands = ledger.candidate_asks(index)
    assert any(person == "Yash" for _n, person, _preview in cands)

    captured = {}

    def fake_call(prompt, schema, fallback):
        captured["prompt"] = prompt
        return {"headline": "", "loops": []}, None

    out = ledger.run_ledger(ctx, fake_call)
    assert "[1] asks @Yash:" in captured["prompt"]
    assert "Nothing open" in out


def test_ledger_union_merges_two_samples(monkeypatch):
    monkeypatch.setattr(ledger, "real_mention_map",
                        lambda ids: {"247265746751488": "Yash"})
    ctx = _ledger_ctx()
    responses = [
        {"headline": "", "loops": [
            {"task": "Push IDFC webview live", "owner": "Yash",
             "asked_by": "Nikhil Saxena", "opened": 1, "last_touch": 1,
             "chases": 2, "status": "open", "due": ""}]},
        {"headline": "", "loops": [
            {"task": "Push IDFC webview live", "owner": "Yash",
             "asked_by": "Nikhil Saxena", "opened": 1, "last_touch": 1,
             "chases": 3, "status": "no_reply", "due": ""},
            {"task": "Share Maruti rate", "owner": "Tanveen",
             "asked_by": "Shashank Mishra", "opened": 1, "last_touch": 1,
             "chases": 1, "status": "open", "due": ""}]},
    ]
    calls = {"n": 0}

    def fake_call(prompt, schema, fallback):
        d = responses[min(calls["n"], 1)]
        calls["n"] += 1
        return d, None

    out = ledger.run_ledger(ctx, fake_call)
    assert "Push IDFC webview live" in out
    assert "Share Maruti rate" in out
    assert "chased 3×" in out
    assert "no reply" in out
    assert calls["n"] == 2


def test_ledger_render_drops_headlines_with_time_words(monkeypatch):
    monkeypatch.setattr(ledger, "real_mention_map", lambda ids: {})
    ctx = _ledger_ctx()
    index, _transcript, _people = ledger.build_transcript(ctx)
    now = ledger._now(ctx)
    loops = [{"task": "item", "owner": "Yash", "asked_by": "Nikhil Saxena",
              "opened": 1, "last_touch": 1, "chases": 1, "status": "open",
              "due": ""}]
    dated = ledger.render_ledger({"headline": "Ship it today", "loops": loops},
                                 index, now, own_names=set())
    assert "> Ship it" not in dated
    clean = ledger.render_ledger({"headline": "Yash holds the webview", "loops": loops},
                                 index, now, own_names=set())
    assert "> Yash holds the webview" in clean
