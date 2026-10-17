#!/usr/bin/env python3
"""Mosaic /pending sandbox CLI.

    python3 sandbox/run.py --list
    python3 sandbox/run.py --approach ledger --approach digest6 --save
    python3 sandbox/run.py --approach ledger --model gemini-3.5-flash-lite --repeat 3
    python3 sandbox/run.py --approach ledger --pulse            # live pulses in Me chat
    python3 sandbox/run.py --all --clean

Compare approaches, pick the winner, then we port it into wacmd.py.
"""

import argparse
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

import approaches  # noqa: E402
from _fmt import banner, blue, bold, box, cyan, dim, green, red, section, set_color, table, yellow  # noqa: E402

import engine  # noqa: E402

DATA_PATH = SANDBOX / "data" / "context.json"
OUT_DIR = SANDBOX / "outputs"


def load_context(path: Path, clean: bool) -> dict:
    if not path.exists():
        raise SystemExit(
            f"no context at {path}\nrun first:  python3 sandbox/dump_context.py --chat \"<group name>\""
        )
    ctx = json.loads(path.read_text())
    ctx["options"] = {"clean": clean}
    return ctx


def make_model(name: str):
    if not engine.GEMINI_API_KEY:
        raise SystemExit(
            "no Gemini key found — put GEMINI_API_KEY in the repo .env (see SETUP.md)"
        )
    import google.generativeai as genai

    return genai.GenerativeModel(name)


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
    """Emulates production /pending UX: progress pulses + final answer in Me chat."""

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
        cfg = {"response_mime_type": "application/json", "response_schema": schema}
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
    runner = Runner(model, temp)

    def cj(prompt, schema, fallback):
        data, err = runner.call_json(prompt, schema, fallback)
        return data, err

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


def print_list():
    print(banner("MOSAIC /pending SANDBOX", [
        "compares prompt/algo variants for the /pending command",
        "pick a winner here, then we merge it into wacmd.py",
    ]))
    print()
    rows = []
    for i, a in enumerate(approaches.APPROACHES, 1):
        tag = cyan("LLM") if a["llm"] else green("offline")
        rows.append([str(i), a["name"], tag, a["window"], a["desc"]])
    print(table(["#", "name", "kind", "window", "what it does"], rows))
    print()
    print(dim("hypotheses:"))
    for a in approaches.APPROACHES:
        print(f"  {bold(a['name']):<28} {dim(a['hypothesis'])}")
    print()
    print("pick with:  " + cyan("python3 sandbox/run.py --approach ledger --approach digest6")
          + dim("   (or --all)"))


def main() -> int:
    ap = argparse.ArgumentParser(description="compare /pending approaches")
    ap.add_argument("--list", action="store_true", help="show approaches and exit")
    ap.add_argument("--approach", action="append", default=[], help="approach name(s)")
    ap.add_argument("--all", action="store_true", help="run every approach")
    ap.add_argument("--dump", action="store_true", help="refresh the data dump first")
    ap.add_argument("--chat", default=os.getenv("SANDBOX_CHAT", ""),
                    help="chat for --dump (required with --dump; any group works)")
    ap.add_argument("--data", default=str(DATA_PATH))
    ap.add_argument("--clean", action="store_true", help="drop /commands and bot digests from context")
    ap.add_argument("--temp", type=float, default=None, help="generation temperature (default: model's)")
    ap.add_argument("--model", default="gemini-2.5-flash-lite")
    ap.add_argument("--repeat", type=int, default=1, help="run each approach N times (variance check)")
    ap.add_argument("--pulse", action="store_true",
                    help="send progress pulses + the final output to the Me chat")
    ap.add_argument("--save", action="store_true", help="save outputs under sandbox/outputs/")
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    set_color(not args.no_color)
    if args.list or (not args.approach and not args.all):
        print_list()
        return 0

    selected = approaches.APPROACHES if args.all else [
        approaches.BY_NAME[n] for n in args.approach
        if n in approaches.BY_NAME
    ]
    unknown = [n for n in args.approach if n not in approaches.BY_NAME]
    if unknown:
        raise SystemExit(f"unknown approach(es): {', '.join(unknown)}")

    if args.dump:
        if not args.chat:
            raise SystemExit('--dump needs a chat:  --chat "<group name>"')
        from dump_context import dump

        ctx = dump(args.chat, Path(args.data))
        print(green(f"✅ context refreshed: {ctx['meta']['total_msgs']} msgs total"))
    ctx = load_context(Path(args.data), clean=args.clean)

    llm_entries = [a for a in selected if a["llm"]]
    n_calls = len(llm_entries) * args.repeat
    meta = ctx["meta"]
    print(banner("MOSAIC /pending SANDBOX", [
        f"chat: {bold(meta['chat_name'])}  ({meta['total_msgs']} msgs · {str(meta['first_ts'])[:10]} → {str(meta['last_ts'])[:10]})",
        f"model: {args.model} · temp: {args.temp if args.temp is not None else 'default'}"
        f" · context: {'cleaned' if args.clean else 'raw'} · repeat: {args.repeat}",
    ]))
    if n_calls > 10 and not args.yes:
        ans = input(f"  this will make ~{n_calls} LLM calls · continue? [y/N] ").strip().lower()
        if ans != "y":
            print(dim("aborted."))
            return 1

    model = make_model(args.model) if llm_entries else None

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    save_dir = OUT_DIR / stamp
    results = []
    for i, entry in enumerate(selected, 1):
        print()
        print(section(f"{i}/{len(selected)}", entry["name"], entry["desc"]))
        runs = []
        first_rendered = ""
        for r in range(args.repeat):
            pulser = None
            if args.pulse and r == 0:
                chat = str(ctx["meta"].get("chat_name") or "")[:40]
                pulser = Pulser(entry["name"], chat)
            if pulser:
                pulser.start()
            t0 = time.time()
            try:
                rendered, data, usage = run_entry(entry, ctx, model, args.temp)
            except Exception as exc:
                rendered, data, usage = red(f"FAILED: {exc}"), None, {"calls": 0, "secs": time.time() - t0, "tok_in": 0, "tok_out": 0}
            if pulser:
                pulser.done(rendered)
            stats = entry.get("stats", lambda d: {})(data) if data is not None else {}
            runs.append({"rendered": rendered, "usage": usage, "stats": stats,
                         "secs": time.time() - t0})
            if r == 0:
                first_rendered = rendered

        print(box(first_rendered))
        run0 = runs[0]
        m = [f"chars {len(first_rendered)}"]
        st = run0["stats"]
        if st.get("inits") is not None:
            m.append(f"inits {st['inits']}")
        if st.get("upd_max") is not None:
            m.append(f"upd≤{st['upd_max']}")
        if st.get("next") is not None:
            m.append(f"next {st['next']}")
        m.append(f"tokens {run0['usage']['tok_in']}→{run0['usage']['tok_out']}")
        m.append(f"{run0['secs']:.1f}s")
        if args.repeat > 1:
            variance = [r["stats"].get("inits") for r in runs]
            m.append(f"runs {variance}")
        print("  " + dim(" · ".join(m)))

        if args.save:
            save_dir.mkdir(parents=True, exist_ok=True)
            for r, run in enumerate(runs):
                (save_dir / f"{entry['name']}-r{r + 1}.txt").write_text(run["rendered"])
        results.append({
            "name": entry["name"], "chars": len(first_rendered),
            "secs": round(run0["secs"], 1),
            "tok_in": run0["usage"]["tok_in"], "tok_out": run0["usage"]["tok_out"],
            "runs": len(runs), "stats": run0["stats"],
        })

    print()
    print(section("∑", "comparison", "smaller chars + fewer inits usually = sharper"))
    rows = []
    for r in results:
        st = r["stats"]
        size = str(r["chars"])
        size = green(size) if r["chars"] < 1500 else yellow(size) if r["chars"] < 3000 else red(size)
        rows.append([
            r["name"],
            size,
            str(st.get("inits", "—")),
            str(st.get("upd_max", "—")),
            str(st.get("next", "—")),
            f"{r['tok_in']}→{r['tok_out']}",
            f"{r['secs']}s",
        ])
    print(table(["approach", "chars", "inits", "upd≤", "next", "tokens", "time"], rows))
    if args.save:
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / "results.json").write_text(json.dumps(
            {"meta": meta, "model": args.model, "temp": args.temp,
             "clean": args.clean, "results": results}, indent=1, ensure_ascii=False))
        print(dim(f"\nsaved → {save_dir}"))
    print()
    print(dim("review the outputs, then tell me the winning approach — we merge it into wacmd.py."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
