# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **New README visual language** — light, Apple-keynote-style hero, problem, bento,
  showcase and setup images (each with a `prefers-color-scheme` dark variant on
  `#0D1117`), all built from one story (same group, one morning, one set of tasks) and
  exported as WebP under 60 KB.
- Problem-first page structure: **The problem** (unread overload + asks dying in the
  scroll), **What it does** bento, compact **Built to be trusted** row, App-Store-style
  **Show me** panels composited two rows × three, and a 1-2-3 setup strip above the
  Railway steps.
- 312-unread tagline ("312 unread messages. 3 things you actually owe. One command to
  find them."); badges move under the deploy button.

### Removed
- The six dark-mode chat screenshots and the old hero (`assets/*.jpg`) — replaced by
  `assets/*-v2.webp` (new filenames to defeat GitHub's image-proxy cache). The dark
  banner remains as the repository **social preview** (`assets/social-cover.png`).

## [2.0.1] - 2026-10-17

### Added
- **Answers name the group they analyzed** — `/sotu`, `/stats` and `/recap` titles now
  include the chat name (e.g. `📊 *Team Stats — Last 14 Days — Launch Squad*`), matching
  `/pending` and `/eli5`; `/eli5` drops the cute "ELI30" prefix for a plain
  `💡 *{topic}* — from *{chat}*` header.
- **Contributing guide** (`CONTRIBUTING.md`) — sandbox lab and model-benchmark how-tos.
- `scripts/` — all diagnostics (`test_api.py`, `test_local.py`, `evaluate_models.py`,
  `gemini_check.py`, `clean.sh`) out of the repo root.

### Changed
- README second pass: unified dark screenshot set (one story, one time), honest FAQ
  (billing-enabled key recommendation matching `docs/RAILWAY.md`), softened model-latency
  claim, "Not affiliated with WhatsApp or Meta" footer line.

## [2.0.0] - 2026-10-17

### Added
- **`/pending` ships the ledger engine (`ledger.py`)**: open loops by *owner* — what
  everyone asked the owner for and vice versa, since when, chased how many times, what's
  overdue. Two model samples are unioned and validated in code (cited transcript numbers
  only); due dates and the overdue ⚠️ flag are computed from the cited messages, never
  hallucinated. Default model: `gemini-2.5-flash-lite` (accuracy parity with larger
  models, ~20× faster).
- **`sandbox/`** — the `/pending` approach lab: per-chat context dumps and a CLI runner
  (`python3 sandbox/run.py --approach ledger --pulse`) with digest/chrono/two-pass/ledger
  strategies for iterating before production.
- **Me-chat delivery (`mechat.py`)**: every command answer (including `/help`) is now delivered to the owner's Me chat (self-chat) — the chat the command was typed in is never written to. Resolution order: `MECHAT_JID` env → pairing store (PN + LID) → freshest self-chat in `messages.db`; unresolved means no send anywhere, loudly logged.
- **Web setup page (Go bridge)**: QR code as auto-refreshing PNG, Gemini-key validity tick, connected view (`Connected as +91… · Me chat: … · last message N min ago`), Unlink button. Behind `SETUP_PASSWORD` (generated + printed in logs when unset).
- **Launch resolver hook**: on connect / reconnect / after history sync the bridge runs `python3 mechat.py --resolve --welcome`; a one-time welcome lands in the Me chat.
- **Deploy support**: `Dockerfile`, `railway.toml`, `railway.json`, `/health` endpoint, `STORE_DIR` volume support, `.env.example`.
- **Offline test suite** (`tests/`): Me-chat resolution, owner gate (PN + LID), routing (answers only to Me chat, zero sends to the source chat), formatter goldens. Run: `python3 -m pytest tests/ -q`.

### Changed
- **Internal send API** is loopback-only (`127.0.0.1:8090`) and requires a shared token; the token is auto-generated (`store/bridge_token`) and passed to the Python engine.
- **Owner check**: session-derived identity (PN or LID, lid_map aware) instead of env-only; `OWNER_PHONE_NUMBER` still honored as a fallback.
- **whatsmeow bumped** to the current client version (older builds are rejected by WhatsApp with `405`).

### Removed
- No invoke-delete: the `/command` message stays exactly as typed (this was never part of wa-slash; explicitly out of scope).

## [1.1.0] - 2026-04-18

### Added
- **Diagnostic Helper (`test_api.py`)**: Added a standalone script to verify Gemini API key validity, testing both standard text generation and strict JSON schema generation.
- **Enhanced Console Visibility**: Added explicit terminal logging when commands are invoked. The terminal will now print `[Command] Context Loaded` with the total messages pulled, the earliest timestamp, and the API payload size to help debug empty responses.

### Changed
- **Dynamic Context Truncation**: Modified the `engine.py` formatting engine to actively trim chat histories down to a maximum character payload (default ~100,000 chars) before passing to the Gemini API. This prioritizes the *most recent* context and prevents `400 Bad Request` or Payload Too Large errors on highly active groups when running commands like `/sotu` or `/recap` which query up to 2,000 messages.

## [1.2.0] - 2026-04-18
### Added
- **AI Model Evaluation Harness (`evaluate_models.py`)**: A powerful testing tool that benchmarks multiple Gemini and Gemma models against your real WhatsApp history. It automatically finds your most active group, runs simulated commands, and uses a "Judge" AI to grade the quality, hallucinations, and context retention of each model.
