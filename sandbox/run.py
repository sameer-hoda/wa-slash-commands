#!/usr/bin/env python3
"""Mosaic sandbox CLI — one lab, every command.

    python3 sandbox/run.py --list
    python3 sandbox/run.py --command sotu  --all --save
    python3 sandbox/run.py --command recap --approach cited --repeat 3
    python3 sandbox/run.py --command eli5  --approach grounded --topic "webview capping"
    python3 sandbox/run.py --command stats --approach leaderboard
    python3 sandbox/run.py --command pending --approach ledger --pulse

Compares approaches per command, saves outputs under
sandbox/outputs/<command>/<stamp>/, then we port the winner into wacmd.py.
"""

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
ROOT = SANDBOX.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SANDBOX))

import approaches  # noqa: E402
import core  # noqa: E402
from _fmt import banner, box, cyan, dim, green, red, section, set_color, table, yellow  # noqa: E402


def print_list(command: str):
    print(banner("MOSAIC SANDBOX", [
        f"command: /{command}  ·  chat: the dumped fixture (sandbox/data/context.json)",
        "pick a winner here, then we merge it into wacmd.py",
    ]))
    print()
    rows = []
    for i, a in enumerate(approaches.registry(command), 1):
        tag = cyan("LLM") if a["llm"] else green("offline")
        rows.append([str(i), a["name"], tag, a["window"], a["desc"]])
    print(table(["#", "name", "kind", "window", "what it does"], rows))
    print()
    print(dim("hypotheses:"))
    for a in approaches.registry(command):
        print(f"  {a['name']:<28} {dim(a['hypothesis'])}")
    print()
    print(dim("commands: " + " · ".join(approaches.COMMANDS)))
    print("pick with:  " + cyan(f"python3 sandbox/run.py --command {command} --approach <name>")
          + dim("   (or --all)"))


def main() -> int:
    ap = argparse.ArgumentParser(description="compare sandbox approaches per command")
    ap.add_argument("--command", default="pending",
                    choices=list(approaches.COMMANDS),
                    help="which slash command's lab to run (default: pending)")
    ap.add_argument("--list", action="store_true", help="show approaches and exit")
    ap.add_argument("--approach", action="append", default=[], help="approach name(s)")
    ap.add_argument("--all", action="store_true", help="run every approach")
    ap.add_argument("--dump", action="store_true", help="refresh the data dump first")
    ap.add_argument("--chat", default="",
                    help="chat for --dump (required with --dump; any group works)")
    ap.add_argument("--data", default=str(core.DATA_PATH))
    ap.add_argument("--clean", action="store_true", help="drop /commands and bot digests from context")
    ap.add_argument("--topic", default="", help="topic for /eli5 approaches")
    ap.add_argument("--temp", type=float, default=core.DEFAULT_TEMP,
                    help="generation temperature (default: 0.1 — the finalized /pending setting)")
    ap.add_argument("--model", default=core.DEFAULT_MODEL,
                    help="model (default: gemini-2.5-flash-lite — the finalized /pending model)")
    ap.add_argument("--repeat", type=int, default=1, help="run each approach N times (variance check)")
    ap.add_argument("--pulse", action="store_true",
                    help="send progress pulses + the final output to the Me chat")
    ap.add_argument("--save", action="store_true", help="save outputs under sandbox/outputs/<command>/")
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    set_color(not args.no_color)
    command = args.command
    if args.list or (not args.approach and not args.all):
        print_list(command)
        return 0

    selected = approaches.registry(command) if args.all else [
        approaches.by_name(command)[n] for n in args.approach
        if n in approaches.by_name(command)
    ]
    unknown = [n for n in args.approach if n not in approaches.by_name(command)]
    if unknown:
        raise SystemExit(f"unknown approach(es) for /{command}: {', '.join(unknown)}")

    if args.dump:
        if not args.chat:
            raise SystemExit('--dump needs a chat:  --chat "<group name>"')
        from dump_context import dump

        ctx = dump(args.chat, Path(args.data))
        print(green(f"✅ context refreshed: {ctx['meta']['total_msgs']} msgs total"))
    ctx = core.load_context(Path(args.data), clean=args.clean, topic=args.topic)

    llm_entries = [a for a in selected if a["llm"]]
    n_calls = len(llm_entries) * args.repeat
    meta = ctx["meta"]
    print(banner(f"MOSAIC SANDBOX · /{command}", [
        f"chat: {meta['chat_name']}  ({meta['total_msgs']} msgs · {str(meta['first_ts'])[:10]} → {str(meta['last_ts'])[:10]})",
        f"model: {args.model} · temp: {args.temp if args.temp is not None else 'default'}"
        f" · context: {'cleaned' if args.clean else 'raw'} · repeat: {args.repeat}"
        + (f" · topic: {args.topic}" if args.topic else ""),
    ]))
    if n_calls > 10 and not args.yes:
        ans = input(f"  this will make ~{n_calls} LLM calls · continue? [y/N] ").strip().lower()
        if ans != "y":
            print(dim("aborted."))
            return 1

    model = core.make_model(args.model) if llm_entries else None

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    save_dir = core.OUT_DIR / command / stamp
    results = []
    for i, entry in enumerate(selected, 1):
        print()
        print(section(f"{i}/{len(selected)}", entry["name"], entry["desc"]))
        runs = []
        first_rendered = ""
        for r in range(args.repeat):
            pulser = None
            if args.pulse and r == 0:
                chat = str(meta.get("chat_name") or "")[:40]
                pulser = core.Pulser(f"/{command} · {entry['name']}", chat)
            if pulser:
                pulser.start()
            t0 = time.time()
            try:
                rendered, data, usage = core.run_entry(entry, ctx, model, args.temp)
            except Exception as exc:
                rendered, data, usage = red(f"FAILED: {exc}"), None, {
                    "calls": 0, "secs": time.time() - t0, "tok_in": 0, "tok_out": 0}
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
        for key in ("inits", "upd_max", "next", "themes", "ask", "events", "points", "people"):
            if st.get(key) is not None:
                m.append(f"{key} {st[key]}")
        m.append(f"tokens {run0['usage']['tok_in']}→{run0['usage']['tok_out']}")
        m.append(f"{run0['secs']:.1f}s")
        if args.repeat > 1:
            m.append(f"chars×{args.repeat} {[len(r['rendered']) for r in runs]}")
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
    print(section("∑", f"/{command} comparison", "smaller chars + fewer inits usually = sharper"))
    rows = []
    for r in results:
        st = r["stats"]
        size = str(r["chars"])
        size = green(size) if r["chars"] < 1500 else yellow(size) if r["chars"] < 3000 else red(size)
        rows.append([
            r["name"],
            size,
            str(st.get("themes", st.get("events", st.get("inits", st.get("people", "—"))))),
            f"{r['tok_in']}→{r['tok_out']}",
            f"{r['secs']}s",
        ])
    print(table(["approach", "chars", "items", "tokens", "time"], rows))
    if args.save:
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / "results.json").write_text(json.dumps(
            {"command": command, "meta": meta, "model": args.model, "temp": args.temp,
             "clean": args.clean, "topic": args.topic, "results": results},
            indent=1, ensure_ascii=False))
        print(dim(f"\nsaved → {save_dir}"))
    print()
    print(dim("review the outputs, then tell the agent/me the winning approach — we merge it into wacmd.py."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
