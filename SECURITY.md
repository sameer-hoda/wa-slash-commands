# Security Policy

## Reporting a vulnerability

Please open a private security advisory or email the maintainer at the address on the
[GitHub profile](https://github.com/sameer-hoda). Do **not** open a public issue for
security reports.

Please include: what's affected, how it can be reproduced, and (if known) a suggested fix.
Expect an acknowledgement within 72 hours.

## Scope

- **Bridge send API** — the Go bridge exposes a send API used by the Python engine. It is
  bound to loopback only and requires a shared token (auto-generated per launch).
- **Setup page** — loopback-only with no password gate on the Mac app (it is reachable
  only from your own Mac). Remove the app's data dir to force a fresh pairing.
- **Pairing data** — WhatsApp session credentials and message history live only under
  `~/Library/Application Support/Mosaic/`. Anyone with access to your Mac login can
  read the linked session and history; FileVault covers the at-rest case.
- **Gemini key** — stored in your Keychain (`com.sameerhoda.mosaic`), passed to child
  processes as an environment variable, never written to disk. Prefer/use a key with
  a spend limit.

Out of scope: WhatsApp account-level risks inherent to unofficial protocol clients
(see the README FAQ).
