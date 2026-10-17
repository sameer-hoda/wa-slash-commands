# Changelog

All notable changes to this project will be documented in this file.

## [2.0.0] - 2026-10-17

### Added
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
