import datetime

import engine
import ledger


def _msgs():
    d1 = datetime.datetime(2026, 10, 15, 6, 30)   # naive UTC
    d2 = datetime.datetime(2026, 10, 16, 5, 0)
    return [("Nikhil Saxena", "@247265746751488 push IDFC live", d1),
            ("Yash", "will check", d2)]


def test_render_pending_two_samples_union(monkeypatch):
    monkeypatch.setattr(ledger, "real_mention_map",
                        lambda ids: {"247265746751488": "Yash"})
    monkeypatch.setattr(ledger, "own_display_names", lambda: set())
    calls = {"n": 0}

    def fake(prompt, fallback, schema=None):
        calls["n"] += 1
        loops = [{"task": "Push IDFC live", "owner": "Yash",
                  "asked_by": "Nikhil Saxena", "opened": 1, "last_touch": 1,
                  "chases": 2, "status": "open", "due": ""}]
        if calls["n"] == 2:
            loops.append({"task": "Share UTM sheet", "owner": "Tanveen",
                          "asked_by": "Shashank Mishra", "opened": 1,
                          "last_touch": 1, "chases": 1, "status": "open",
                          "due": "Monday"})
        return {"headline": "Yash owns IDFC", "loops": loops}

    monkeypatch.setattr(engine, "gemini_json", fake)
    out = ledger.render_pending("1@g.us", _msgs(), chat_name="Branding OKR")

    assert calls["n"] == 2
    assert "📌 *Pending — Branding OKR*" in out
    assert "Push IDFC live" in out
    assert "Share UTM sheet" in out
    assert "> Yash owns IDFC" in out


def test_render_pending_returns_none_when_both_fail(monkeypatch):
    monkeypatch.setattr(engine, "gemini_json",
                        lambda p, f, s=None: {**f, "_gemini_failed": True})
    assert ledger.render_pending("1@g.us", _msgs(), chat_name="X") is None


def test_render_pending_survives_one_failed_sample(monkeypatch):
    monkeypatch.setattr(ledger, "real_mention_map", lambda ids: {})
    monkeypatch.setattr(ledger, "own_display_names", lambda: set())
    calls = {"n": 0}

    def fake(prompt, fallback, schema=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {**fallback, "_gemini_failed": True}
        return {"headline": "", "loops": [
            {"task": "Fix Dreame webview", "owner": "Yash", "asked_by": "Nikhil",
             "opened": 1, "last_touch": 1, "chases": 1, "status": "open",
             "due": ""}]}

    monkeypatch.setattr(engine, "gemini_json", fake)
    out = ledger.render_pending("1@g.us", _msgs(), chat_name="X")

    assert "Fix Dreame webview" in out
    assert calls["n"] == 2
