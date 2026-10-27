# Railway path — deprecated

> The hosted Railway deploy is retired for security reasons: it kept a copy of
> the WhatsApp session, a public setup URL, and a send-capable API on shared
> infrastructure. New installs should use the Mac DMG (see
> `docs/MAC_DMG_SPEC_V2.md`). The files below remain in git history only.

## If you already run on Railway

1. On your phone, open WhatsApp → **Linked devices** → remove the old device.
2. In Railway, delete the service **volume** (`/data`) so the pairing dies with it.
3. Install the Mac DMG and re-pair locally. Do **not** copy `whatsapp.db`
   between installs — fresh pairing is safer than transplanting session keys.

## Files kept for history (do not use for new installs)

- `railway.json` / `railway.toml` — old deploy config.
- `Dockerfile` — old Railway runtime (`STORE_DIR=/data`).
- `deploy-railway.sh` — old one-command deploy.
- `docs/RAILWAY.md` — old full guide.
