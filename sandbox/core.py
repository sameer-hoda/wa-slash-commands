#!/usr/bin/env python3
"""Shared runner + helpers for the Mosaic sandbox lab.

One engine, every command (/pending /sotu /recap /stats /eli5):

  - load_context()     → read the branding-OKR fixture (sandbox/data/context.json)
  - make_model()       → Gemini model for sandbox runs (default: the finalized
                         gemini-2.5-flash-lite)
  - Runner             → call_json / call_text with usage accounting
  - run_entry()        → execute one approach (build+render or custom_run)
  - Pulser / me_send   → optional live pulses + final output in the Me chat
  - formatted_window() → engine-style [HH:MM IST] transcript (the "asis" input)
  - numbered_window()  → ledger-style numbered, day-labelled transcript (the
                         code-first input every "cited" approach should reuse)

Approach modules live in sandbox/approaches/<command>.py and are executed by
sandbox/run.py --command <command>.
"""

import datetime
import json
import os
import sys
import threading
import time
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
ROOT = SANDBOX.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SANDBOX))

import engine  # noqa: E402
from _fmt import dim, green, red, yellow  # noqa: E402

DATA_PATH = SANDBOX / "data" / "context.json"
OUT_DIR = SANDBOX / "outputs"
DEFAULT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_TEMP = 0.1


# ── context ───────────────────────────────────────────────────────────────────

def load_context(path=DATA_PATH, clean: bool = False, topic: str = "") -> dict:
    path = Path(path)
    if not path.exists():
        raise SystemExit(
            f"no context at {path}\nrun first:  python3 sandbox/dump_context.py --chat \"<group name>\""
        )
    ctx = json.loads(path.read_text())
    ctx["options"] = {"clean": clean, "topic": topic}
    return ctx


def formatted_window(ctx: dict, window: str) -> str:
    """engine-style transcript: [HH:MM IST] Sender: content (asis approaches)."""
    w = ctx["windows"][window]
    msgs = []
    for m in w["messages"]:
        ts = datetime.datetime.fromisoformat(m["ts"]) if m.get("ts") else None
        msgs.append((m["sender"], m["content"], ts))
    if ctx.get("options", {}).get("clean"):
        from ledger import is_bot_noise

        msgs = [m for m in msgs if not is_bot_noise(m[1])]
    return engine.format_messages_ist(msgs)


def numbered_window(ctx: dict, window: str, max_msgs: int = 500):
    """ledger-style numbered, cleaned, IST/day-labelled transcript.

    Returns (index, transcript, people) — code owns every date the user sees;
    the model only classifies and cites message numbers.
    """
    import ledger

    return ledger.build_transcript(ctx, window, max_msgs)


# ── model / calls ─────────────────────────────────────────────────────────────

def make_model(name: str = DEFAULT_MODEL):
    if not engine.GEMINI_API_KEY:
        raise SystemExit(
            "no Gemini key found — put GEMINI_API_KEY in the repo .env (see SETUP.md)"
        )
    import google.generativeai as genai

    return genai.GenerativeModel(name)


def usage_of(resp) -> dict:
    u = getattr(resp, "usage_metadata", None)
    if not u:
        return {"in": 0, "out": 0}
    return {
        "in": getattr(u, "prompt_token_count", 0) or 0,
        "out": getattr(u, "candidates_token_count", 0) or 0,
    }


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


class Runner:
    def __init__(self, model, temp):
        self.model = model
        self.temp = temp
        self.calls: list[dict] = []

    def call_json(self, prompt, schema, fallback):
        cfg = {"response_mime_type": "application/json"}
        if schema:
            cfg["response_schema"] = schema
        self.call_config(cfg)
        t0 = time.time()
        resp = self.model.generate_content(prompt, generation_config=cfg)
        self.calls.append({"secs": time.time() - t0, **usage_of(resp)})
        try:
            return parse_json(resp.text), None
        except Exception:
            return fallback, "json-parse"

    def call_text(self, prompt):
        cfg = {}
        self.call_config(cfg)
        t0 = time.time()
        resp = self.model.generate_content(prompt, generation_config=cfg or None)
        self.calls.append({"secs": time.time() - t0, **usage_of(resp)})
        return (resp.text or "").strip(), None

    def call_config(self, cfg):
        if self.temp is not None:
            cfg["temperature"] = self.temp


def run_entry(entry, ctx, model, temp):
    """Execute one approach entry → (rendered, data, usage)."""
    runner = Runner(model, temp)

    def cj(prompt, schema, fallback):
        return runner.call_json(prompt, schema, fallback)

    def ct(prompt):
        return runner.call_text(prompt)

    if "custom_run" in entry:
        if entry["llm"]:
            rendered = entry["custom_run"](ctx, cj)
        else:
            rendered = entry["custom_run"](ctx)
        data = None
    elif entry.get("build"):
        built = entry["build"](ctx)
        if isinstance(built, tuple) and len(built) == 3:
            prompt, schema, fallback = built
            data, _err = cj(prompt, schema, fallback)
            rendered = entry["render"](data)
        else:
            text, _err = ct(built)
            data, rendered = None, entry["render"](text)
    else:
        raise RuntimeError(f"approach {entry['name']} has no runner")

    secs = sum(c["secs"] for c in runner.calls)
    toks_in = sum(c["in"] for c in runner.calls)
    toks_out = sum(c["out"] for c in runner.calls)
    return rendered, data, {"calls": len(runner.calls), "secs": secs,
                            "tok_in": toks_in, "tok_out": toks_out}


# ── Me chat pulses (optional) ─────────────────────────────────────────────────

def me_send(text: str) -> bool:
    """Send to the resolved Me chat via the running bridge (pulse mode)."""
    import requests

    from mechat import bridge_token, get_mechat_jid

    jid = get_mechat_jid()
    if not jid:
        return False
    headers = {}
    token = bridge_token()
    if token:
        headers["X-Bridge-Token"] = token
    try:
        resp = requests.post(
            os.getenv("WA_API_URL", "http://127.0.0.1:8090/api/send"),
            json={"recipient": jid, "message": text},
            headers=headers, timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


class Pulser:
    """Emulates production UX: progress pulses + final answer in Me chat."""

    def __init__(self, label: str, chat: str = ""):
        self.label = label
        self.chat = chat
        self.t0 = time.time()
        self.ticks = 0
        self.timer = None
        self.alive = False

    def start(self):
        where = f" on *{self.chat}*" if self.chat else ""
        if not me_send(f"🧪 _sandbox · {self.label}_{where} · ⏳ working on it — reading the chat…"):
            print(yellow("  ⚠️ pulse: Me chat send failed (bridge running?)"))
            return False
        self.alive = True
        self._schedule()
        return True

    def _schedule(self):
        if self.ticks >= 3:
            return
        self.ticks += 1
        self.timer = threading.Timer(20, self._tick)
        self.timer.daemon = True
        self.timer.start()

    def _tick(self):
        if not self.alive:
            return
        if me_send(f"⏳ still working… {int(time.time() - self.t0)}s"):
            self._schedule()

    def done(self, rendered: str):
        self.alive = False
        if self.timer:
            self.timer.cancel()
        me_send(f"🧪 _sandbox · {self.label}_\n\n{rendered}")
