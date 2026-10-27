# Mac DMG Spec v2 — wa-slash-commands local-first (Apple Silicon)

> Status: draft for review. v1 was `docs/MAC_DMG_SPEC.md`. This v2 folds in the
> validation feedback (reliability + security contradictions + UI). No code built yet.

## 1. Goal

Ship wa-slash-commands as a native Mac app for Apple Silicon, distributed as a
signed + notarized DMG, and retire the Railway deploy path.

First-run onboarding: enter Gemini API key → live validation → WhatsApp pair
(QR + phone-number option) → Me-chat confirmation → Start at Login choice →
live `/help` proof. Then run locally, supervised, with auto-updates.

## 2. Naming (decided here, changes are expensive later)

- Product name: **Mosaic**.
- Bundle ID: **`com.sameerhoda.mosaic`** (placeholder — confirm before first signing;
  renaming later breaks Keychain items, login items, and data paths).
- Data dir: `~/Library/Application Support/Mosaic/`.
- One name everywhere: DMG, `.app`, menu bar, Settings, docs. No more mixing
  "wa-slash-commands" and "Mosaic" in user-visible surfaces.

## 3. Context (what exists today)

`sameer-hoda/wa-slash-commands`, branch `master`, Python + Go (whatsmeow):

- [wacmd.py](/Users/sameerhoda/Projects/wa_master/wa-slash-commands/wacmd.py) — slash commands
  (`/sotu`, `/pending`, `/stats`, `/recap`, `/eli5`, `/help`). Answers go to the
  owner's Me chat only.
- [engine.py](/Users/sameerhoda/Projects/wa_master/wa-slash-commands/engine.py) — Gemini calls
  (`gemini-2.5-flash-lite`, confirm at build time) with JSON schema, reads
  `store/messages.db`, per-chat cache in `cache/`.
- [mechat.py](/Users/sameerhoda/Projects/wa_master/wa-slash-commands/mechat.py) — Me-chat resolution
  (explicit `MECHAT_JID` → session PN/LID → freshest self-chat), fails loud.
- [bridge/main.go](/Users/sameerhoda/Projects/wa_master/wa-slash-commands/bridge/main.go) +
  [bridge/setup_web.go](/Users/sameerhoda/Projects/wa_master/wa-slash-commands/bridge/setup_web.go) —
  WhatsApp Web session, `STORE_DIR` persistence (`whatsapp.db`, `messages.db`,
  `mechat.json`, `bridge_token`), per-`/command` `wacmd.py` spawn, setup page
  with QR + Gemini tick + Unlink behind a password.
- [scripts/gemini_check.py](/Users/sameerhoda/Projects/wa_master/wa-slash-commands/scripts/gemini_check.py) —
  key check via `list_models` (v2 extends this, see §6).
- Railway today: [railway.json](/Users/sameerhoda/Projects/wa_master/wa-slash-commands/railway.json),
  [railway.toml](/Users/sameerhoda/Projects/wa_master/wa-slash-commands/railway.toml),
  `Dockerfile` (`STORE_DIR=/data`), `deploy-railway.sh`, [docs/RAILWAY.md](/Users/sameerhoda/Projects/wa_master/wa-slash-commands/docs/RAILWAY.md),
  README Deploy button.

## 4. Problem statement

Railway keeps a cloud copy of the WhatsApp session, a public setup URL, and a
key/billing surface the owner cannot see or revoke locally. Session DBs and a
send-capable API on shared infra + pairing over the public internet is the risk
being removed.

Local-first fix: bridge + Python engine + SQLite live only on the user's Mac,
key lives in Keychain only, no remote listener, no hosted path. Disclose in
README + onboarding: unofficial WhatsApp clients carry account risk, and
messages the user asks about are sent to Google Gemini for summarising.

## 5. Architecture (v2 corrections applied)

- **Native shell, no localhost TCP.** Onboarding + Settings are SwiftUI. The Go
  bridge emits events as JSON lines on stdout (`qr`, `scanned`, `connected`,
  `logged_out`, `heartbeat`); the Swift shell renders them. No `SETUP_PASSWORD`,
  no `PORT`, no `/health` listener. If HTML must be reused, load it in WKWebView
  with a custom URL scheme, never a TCP port.
- **IPC over Unix domain socket, not HTTP.** Socket lives in Application Support
  with `0600`. Deletes `WA_API_URL` loopback HTTP and `bridge_token` network
  surface entirely.
- **One long-lived Python worker.** Spawning embedded Python per `/command`
  costs ~1–2s. Run a single worker over the socket; the supervisor restarts it.
  Reuse `engine.py` / `formatter.py` / `mechat.py` / `ledger.py` logic inside it.
- **Supervisor (Swift owns Go + Python).** Restart with exponential backoff,
  heartbeat ping every ~30s, crash-loop guard (e.g. 5 crashes in 2 min → error
  state with reason, no infinite restart).
- **Single instance.** Lock file in Application Support. Two bridges on one
  whatsmeow session fight and disconnect each other.
- **Keychain only, no plaintext fallback.** Swift reads Keychain and passes the
  key to children via env/stdin. Python never touches Keychain (avoids repeated
  allow-prompts across signing-identity changes).
- **SDK migration.** `google-generativeai` is deprecated → migrate to
  `google-genai` now. Confirm the model ID at build time, don't trust the spec.
- **Bundling.** `arm64` only, no Universal in v1 (suggest macOS 14+ floor).
  Use python-build-standalone or Briefcase. Sign every `.so`/`.dylib`/binary
  with hardened runtime, set `PYTHONDONTWRITEBYTECODE=1`, ship precompiled
  `.pyc` (writing into the bundle breaks the signature). Expect to need the
  `disable-library-validation` entitlement for Python extensions — test early,
  it is the most common notarization blocker.
- **Auto-update in v1.** Ship Sparkle 2 with EdDSA-signed appcast. whatsmeow
  breaks when WhatsApp changes protocol; manual DMG reinstalls leave every user
  offline. Costs ~1 day, required.

## 6. Gemini key validation (real, at onboarding)

`list_models` alone only proves the key exists. v2 requires, debounced on paste:

1. Key present and looks like a Gemini key (hint otherwise).
2. Pinned model appears in the list.
3. A 1-token `generateContent` call succeeds.

This catches region blocks, billing problems, and quota errors before the first
`/recap`. Show the specific error inline under the field. Valid → green tick →
Next enabled. "Paste" button + show/hide field.

## 7. Onboarding (one window, step dots, Back, resume mid-way)

1. **Welcome** — what it is, what you need, privacy line from §4.
2. **Key** — as §6.
3. **Pair** — large QR (auto-refresh + countdown + manual Refresh) on the left,
   3-step phone illustration on the right. Animate Scan → Syncing → Connected.
   Offer **link with phone number** (whatsmeow pairing codes) for camera/QR
   failures and VoiceOver users.
4. **Me chat** — "Send yourself any message now", auto-advance on detection
   (no manual Retry). Show `Connected as +91 ••••• 4321`. Never proceed guessed.
5. **Launch** — Start at Login toggle (default on) via `SMAppService.mainApp`;
   always read live status (users can flip it in System Settings); handle
   `.requiresApproval`. Note "runs quietly in menu bar". Plainly state the Mac
   must be awake; optionally offer "prevent sleep while plugged in".
6. **Done (magic moment)** — "Type `/help` in any chat." Show a live check the
   instant the first command is received and answered end-to-end (beats a Test
   button).

## 8. Runtime reliability

- **Sleep/wake policy.** Commands arriving while asleep burst on wake: answer
  those < ~10 min old, reply "skipped (Mac was asleep)" for older ones (never
  silently drop, never flood). Dedupe by message ID in `ledger.py` so reconnects
  never double-answer. Reconnect on wake + network change (`NWPathMonitor`).
- **Loop guard.** The app's own Me-chat messages must never parse as commands.
- **Phone-side logout.** Detect logout event → menu bar "Logged out — re-scan"
  + actionable notification. Keep `messages.db` history across re-pair.
- **Unlink = `Logout()` then wipe.** Call whatsmeow `Logout()` first or the
  phone keeps a ghost device with live session keys; then wipe pairing DBs.
- **SQLite.** WAL mode, `busy_timeout`, single writer. Clear "disk full" error,
  never silent corruption.
- **Gemini error taxonomy** (Me chat + app, each distinct): invalid key,
  permission/region, 429 quota (with retry time), 5xx, offline. Preserves the
  "fail loud" invariant.
- **Retention.** Setting: 30 / 90 days / forever + periodic vacuum.
  `messages.db` grows forever otherwise.
- **Logs.** Rotate, redact message text + key. "Copy diagnostics" zips redacted
  logs + versions for bug reports.

## 9. Menu bar + Settings (native, alive)

- Template icon + state badge by shape, not color alone (connected / attention /
  error). Popover: status line, last activity ("`/recap` in Family · 2m ago"),
  model/quota hint, 4–5 actions. Destructive Unlink/Uninstall live in Settings
  only.
- Settings is a native SwiftUI `Settings` scene: General (login, sleep), Gemini,
  WhatsApp, Privacy (retention, wipe), Advanced (logs, diagnostics).
- Notifications only for action-needed (logged out, key invalid, quota). Never
  "all good". Full dark mode, keyboard nav, VoiceOver labels, Reduce Motion.

## 10. Packaging + signing

- DMG via `create-dmg`/`hdiutil`: drag-to-Applications, icon, background,
  license. Code-sign Developer ID + notarize + staple (app and DMG).
- CI on `macos-14` arm64 with `notarytool` + App Store Connect API key. Gate on
  `codesign --verify --deep --strict` and `spctl -a -vvv`.
- **Uninstall…** action (required — Trash-drag leaves residue): Logout, wipe
  data, delete Keychain item, unregister login item, quit.

## 11. Railway retirement (secure)

Delete, don't archive in-tree (git history is the archive): remove Deploy
button, `deploy-railway.sh`, `railway.json`/`railway.toml`, `Dockerfile`
Railway path, `docs/RAILWAY.md` → replaced by short
`docs/RAILWAY_DEPRECATED.md`. Migration for existing users: remove old device
under phone Linked Devices, delete Railway volume, re-pair locally (safer than
copying `whatsapp.db`).

## 12. Validation plan (extends v1)

- Fresh Apple Silicon install → onboard → all six commands → reboot with login
  item on → reconnects without re-scan.
- Negatives: empty/fake key, offline Gemini, expired QR, unresolved Me chat —
  each blocks with its message.
- Sleep/wake: lid closed 1h with commands inbound → burst policy from §8.
- Kill `-9` bridge, then Python worker → auto-recovery. Two app copies at once
  → single-instance wins. Wi-Fi toggle mid-command → no duplicate answer.
- Upgrade v1.0 → v1.1 via Sparkle keeps pairing, key, history.
- Phone-side logout + Keychain-deny paths. Disk-full → clear error.
- Gatekeeper on clean Mac; signature + staple verify. Uninstall leaves no login
  item / Keychain / process.
- Regression: seeded-DB outputs match baseline; `pytest tests/ -q` green.

## 13. Risks / open questions

- WhatsApp protocol drift (whatsmeow) is the top outage cause → Sparkle mitigates.
- Python-extension signing (`disable-library-validation`) is the top
  notarization risk → spike early.
- Confirm `google-genai` API + model ID at build start.
- Open: exact macOS floor, Sparkle appcast hosting, DMG background/icon design,
  ToS-risk wording sign-off.

## Sources

- https://www.revenera.com/blog/software-installation/apples-application-notarization-for-macos/
- https://github.com/create-dmg/create-dmg
- https://github.com/google/elephant-goldfish-model


