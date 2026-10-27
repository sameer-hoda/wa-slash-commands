## Goal

Ship wa-slash-commands as a native Mac app for Apple Silicon, distributed as a signed DMG, and retire the Railway deploy path. First-run onboarding: enter Gemini API key, validate it live, scan WhatsApp QR, confirm Me chat, then run locally with optional Start at Login.

## Success Criteria

- A user on an Apple Silicon Mac downloads one DMG, drags one `.app` to Applications, and completes onboarding without touching Terminal, Go, Python, or `.env`.
- Onboarding enforces this order: Gemini key (must validate before continuing) → WhatsApp QR pair → Me-chat confirmation → Start-at-Login choice → done.
- WhatsApp pairing, message history, and settings live only on that Mac. No Railway container, volume, or public URL remains in the happy path.
- The app keeps running across reboots when Start at Login is on, and a normal user can quit, relaunch, unlink, rotate the key, and uninstall cleanly.
- Railway files and docs are removed or clearly marked deprecated so no new user deploys there.

## Context

wa-slash-commands today (`sameer-hoda/wa-slash-commands`, branch `master`) is a Python + Go (whatsmeow) project:

- `wacmd.py` is the slash-command entry point (`/sotu`, `/pending`, `/stats`, `/recap`, `/eli5`, `/help`). Every answer goes to the owner's Me chat only, never back to the group.
- `engine.py` calls Gemini (`gemini-2.5-flash-lite`) with strict JSON schema, reads `store/messages.db`, and caches per chat in `cache/`.
- `mechat.py` resolves the Me chat (explicit `MECHAT_JID` → session PN/LID → freshest self-chat) and fails loud rather than guessing.
- `bridge/main.go` + `bridge/setup_web.go` run the WhatsApp Web session, persist pairing in `STORE_DIR` (`whatsapp.db`, `messages.db`, `mechat.json`, `bridge_token`), call `wacmd.py` per `/command`, and serve the setup page (`/`, `/health`, QR PNG, Gemini-key tick, Unlink) behind a setup password.
- `scripts/gemini_check.py` already validates a key by calling `list_models` and printing `valid | invalid | missing`.
- Current distribution is Railway: `railway.json` + `railway.toml` (Dockerfile builder, `/health` check, 1 replica), `Dockerfile` (Go build → Python runtime, `STORE_DIR=/data`), `deploy-railway.sh`, `docs/RAILWAY.md`, and the Deploy-on-Railway button in `README.md`.

## Problem Statement

Railway keeps a cloud copy of the WhatsApp session, a public setup URL with a password, and a billing/key surface the owner cannot see or revoke locally. That is the security concern: session databases and a send-capable API sitting on shared infrastructure, plus QR/pairing over the public internet. The fix is local-first: move the bridge, Python engine, and SQLite stores onto the user's own Mac, keep the Gemini key in the Mac Keychain / local config, and delete the hosted path so there is nothing remote to breach.

## Approach

Build one Apple Silicon `.app` bundle shipped inside a signed, notarized DMG. The bundle embeds the existing behavior, not a rewrite:

- Reuse as-is: `wacmd.py`, `engine.py`, `formatter.py`, `mechat.py`, `ledger.py`, the whatsmeow bridge logic, and the Me-chat resolution order.
- Replace only the transport: the current web setup page becomes a native onboarding window (or a localhost-only page hosted by the app, never exposed publicly). No `SETUP_PASSWORD`, no `PORT`, no `/health` for Railway.
- Data dir moves to the Mac convention, e.g. `~/Library/Application Support/Mosaic/` (SQLite DBs, `mechat.json`, token, logs). Key goes to Keychain with a config-file fallback. Nothing under the repo's `./store/` ships with the DMG.
- Start at Login is a user-visible toggle (default on, changeable in Settings), implemented with the current macOS login-item mechanism and verified against current Apple docs during build. The app runs as a menu-bar agent, not a dock app that must stay open.
- Target: Apple Silicon only (`arm64`), one architecture, no Universal binary in v1. Minimum macOS version to be pinned during build (suggest macOS 14+ unless a reason to go lower appears).

### Onboarding journey (crisp, no dead ends)

1. Welcome: what this is (private answers in your Me chat), what you need (Gemini key, your phone).
2. Gemini key: paste field with show/hide, link to Google AI Studio, inline Validate button using the existing `list_models` check. Invalid/empty blocks Next with the exact reason (missing, invalid, quota/network). Valid shows a green tick and enables Next.
3. WhatsApp pair: large QR with auto-refresh, countdown, and manual Refresh. Same pairing semantics as today (Linked Devices → Link a device). States: waiting → scanned → connected as `+91…`.
4. Me-chat check: show resolved identity (`Connected as +91… · Me chat: …`). If unresolved, guide the user to message themselves once, with Retry. Never proceed on a guessed chat.
5. Launch behavior: Start at Login toggle (default on) + "Launch quietly in menu bar" note.
6. Done: one-click Test (`/help` to Me chat), links to commands, where data lives, how to quit/unlink.

### App runtime (menu bar)

- Status: Connected / Waiting for QR / Gemini key needed / Error with one-line reason.
- Actions: Open Setup, Re-scan QR, Change Gemini key, Toggle Start at Login, View logs, Unlink WhatsApp (wipes pairing DBs after confirm), Quit.
- Fails loud: Gemini down → explicit error in Me chat and in the app, never a fake "all clear". Same invariant as today.

## Steps

1. Freeze current behavior: record `/help`, `/recap`, `/pending`, `/stats`, `/sotu`, `/eli5` outputs on a seeded local DB (`tests/`, `sandbox/`) as the regression baseline.
2. Define the Mac bundle: `.app` layout, embedded Python runtime + dependencies (`google-generativeai`, `python-dotenv`, `requests`), embedded `arm64` `wa-bridge` binary, `STORE_DIR` override to Application Support, Keychain read/write for the key.
3. Build the onboarding window + menu-bar shell (native shell, localhost-only UI if web is reused). Wire it to existing hooks: `scripts/gemini_check.py` for validation, bridge QR events for pairing, `mechat.py --resolve --welcome` for the Me-chat gate.
4. Implement Start at Login toggle, Unlink/wipe, log viewer, and Test-to-Me-chat. Add Sparkle-style or manual update check (decision: v1 can be manual download; state it).
5. Package the DMG: drag-to-Applications layout, icon, background, license link. Code-sign with Developer ID, notarize, and staple the ticket (installer and app).
6. Retire Railway: remove the Deploy button, `deploy-railway.sh`, Railway dashboard instructions, and `railway.json`/`railway.toml` health-check path from the happy path. Keep at most a short `docs/RAILWAY_DEPRECATED.md` explaining shutdown and migration (export `/data`, re-pair locally). Decide: delete vs. archive, and whether existing Railway users get a migration script.
7. Docs + release: rewrite `README.md` quick start (Download DMG → drag → onboard), update `SETUP.md`, add uninstall instructions, publish the DMG as a GitHub Release asset with checksum.

## Validation Plan

- Fresh-Mac test: new user account on an Apple Silicon Mac, install DMG, complete onboarding with a real key and real QR, run all six commands, reboot with Start at Login on and confirm the app reconnects without re-scan.
- Negative tests: empty key, fake key, offline Gemini, expired QR, no self-message yet (Me-chat unresolved). Each must block with a specific message, never proceed silently.
- Regression: seeded-DB command outputs match the pre-freeze baseline; `python3 -m pytest tests/ -q` stays green.
- Gatekeeper test: download the DMG on a clean Mac (no dev certs), double-click, confirm no "unidentified developer" block; verify signature and stapled ticket.
- Uninstall test: Quit → drag to Trash → confirm no background process remains and Application Support data is either removed or explicitly kept per the doc.

## Risks / Open Questions

- Apple Developer ID + notarization is required for a no-warning DMG install. Needs an Apple Developer account, signing in CI, and a stapled ticket. Unsigned builds will hit Gatekeeper.
- Bundling Python + Go + SQLite for `arm64` is the main size/complexity cost. Alternatives (system Python, Homebrew Go) are rejected for v1 because they break the "no Terminal" goal.
- WhatsApp Web sessions can expire or get logged out by phone-side actions. The app must handle re-pair gracefully (same QR flow, history preserved).
- Gemini model name (`gemini-2.5-flash-lite`) and `google-generativeai` SDK drift should be pinned and smoke-tested at build time.
- Open: minimum macOS version, manual vs. auto-update, and whether Intel Macs are explicitly unsupported in v1. Suggested defaults: Apple Silicon only, macOS 14+, manual updates in v1.

## Sources

- https://www.revenera.com/blog/software-installation/apples-application-notarization-for-macos/
- https://github.com/create-dmg/create-dmg
