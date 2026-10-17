# Security Policy

## Reporting a vulnerability

Please open a private security advisory or email the maintainer at the address on the
[GitHub profile](https://github.com/sameer-hoda). Do **not** open a public issue for
security reports.

Please include: what's affected, how it can be reproduced, and (if known) a suggested fix.
Expect an acknowledgement within 72 hours.

## Scope

- **Bridge send API** — the Go bridge exposes a send API used by the Python engine. It is
  bound to loopback only and requires a shared token (`store/bridge_token`, auto-generated).
- **Setup page** — behind `SETUP_PASSWORD`. If you leave it unset, a password is generated
  at boot and printed in the logs.
- **Pairing data** — WhatsApp session credentials live in `store/whatsapp.db` and your
  message history in `store/messages.db`. Back these up privately; anyone with access to
  the volume can read the linked session and history.
- **Gemini key** — stored in your environment (`GEMINI_API_KEY`) or Railway variables.
  Never commit it, and prefer/use a key with a spend limit.

Out of scope: WhatsApp account-level risks inherent to unofficial protocol clients
(see the README FAQ).
