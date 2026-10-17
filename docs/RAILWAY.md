# Deploy on Railway — full guide

One container, one volume, ~5 minutes. After this you type `/pending` in any
WhatsApp group and the answer lands in your Me chat.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template?template=https://github.com/sameer-hoda/wa-slash-commands)

**You need:** a free [Railway account](https://railway.com) and a
[Gemini API key](https://aistudio.google.com/apikey) from a billing-enabled project.

## Option A — one command (recommended)

macOS, Linux or WSL. Needs only `curl` and `git`:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/sameer-hoda/wa-slash-commands/master/deploy-railway.sh)
```

Or from a clone: `./deploy-railway.sh`.

It asks two questions — your **Gemini key** (checked with Google before anything
is created) and a **setup password** (press Enter to generate one) — then:

| step | what it runs |
|---|---|
| install the CLI if missing | `bash <(curl -fsSL https://railway.com/install.sh) -y` |
| sign in (opens a browser) | `railway login` |
| create project + service | `railway init --name wa-slash-commands` · `railway add --service mosaic` |
| attach storage | `railway volume add --mount-path /data` |
| set variables (secrets via stdin) | `railway variable set GEMINI_API_KEY --stdin` · `SETUP_PASSWORD` · `TZ` |
| build and deploy | `railway up --detach -y` |
| public URL | `railway domain` |
| wait, then open the page | polls `/health` |

Then go to **[4. First boot / pairing](#4-first-boot--pairing)**: log in, scan the QR.

**Updating:** run the same command again in the same folder. It detects the
linked project, updates the variables and code, and keeps the volume, so you
don't re-scan. Overrides: `PROJECT_NAME`, `SERVICE_NAME`, `TZ_VALUE`
(e.g. `TZ_VALUE=Europe/London ./deploy-railway.sh`).

## Option B — Railway CLI, step by step

The same steps by hand, from the repo root:

```bash
# 1. install + sign in
bash <(curl -fsSL https://railway.com/install.sh) -y     # or: brew install railway / npm i -g @railway/cli
railway login

# 2. project, service, volume
railway init --name wa-slash-commands
railway add --service mosaic
railway service mosaic                    # link it, so later commands target it
railway volume add --mount-path /data     # REQUIRED — holds your WhatsApp pairing

# 3. variables (typing the secret on stdin keeps it out of shell history)
railway variable set GEMINI_API_KEY --stdin --skip-deploys     # paste key, then Ctrl-D
railway variable set SETUP_PASSWORD --stdin --skip-deploys     # type password, then Ctrl-D
railway variable set TZ=Asia/Kolkata --skip-deploys

# 4. deploy + URL
railway up --ci
railway domain                            # prints https://<name>.up.railway.app
```

Open the printed URL and continue at **4. First boot / pairing**.

## Option C — dashboard / button

## 1. Deploy the service

- **Button / template:** click the button above, pick your account, deploy.
- **From GitHub:** Railway → New Project → Deploy from GitHub repo →
  `sameer-hoda/wa-slash-commands`.

Then do steps 2–3 below in the dashboard.

Railway reads `railway.toml`: Docker builder, healthcheck `/health`, restart on
failure, `numReplicas = 1`. Build takes a few minutes the first time (Go bridge
+ Python runtime in one image).

## 2. Volume (required)

Service → **Settings → Volumes → New volume → mount path `/data`**.

Why: the container runs with `STORE_DIR=/data`, which holds
`whatsapp.db` (your pairing), `messages.db` (chat history),
`mechat.json` (the resolved Me chat) and `bridge_token`.
Without the volume you lose pairing and history on **every redeploy**.

Keep exactly **one replica** — two replicas would run two bots on one number
(the config pins this; don't override it).

## 3. Variables

Service → **Variables**:

| variable | required | notes |
|---|---|---|
| `GEMINI_API_KEY` | yes | billing-enabled key. Free-tier content is used by Google to improve products; paid-tier is not |
| `SETUP_PASSWORD` | recommended | locks the setup page. If unset, one is generated and printed in the deploy logs on every boot |
| `TZ` | optional | default `Asia/Kolkata` |
| `PORT` | auto | Railway injects it; don't set it yourself |

Then **Settings → Networking → Generate Domain** to get a public URL.

## 4. First boot / pairing

1. Open **Deployments → View Logs** and find the `SETUP PASSWORD` box
   (skip this if you set `SETUP_PASSWORD`).
2. Open your service URL → enter the password.
3. Scan the QR: WhatsApp → **Linked devices → Link a device**. The QR
   auto-refreshes every 2 s.
4. Within seconds the page shows:
   `Connected as +91… · Me chat: …` — plus a Gemini-key validity tick.
5. A welcome message lands in your Me chat: `✅ Mosaic is connected.`

If it shows **Me chat: NOT FOUND YET**, send any message to yourself
("Message yourself"), then wait ~1 minute (reconnect/history resolves it).
Answers are never delivered to a guessed chat — unresolved means it stays quiet.

## 5. Verify

- `https://<your-domain>/health` → `{"ok":true, ...}` (works even before pairing,
  so Railway's healthcheck never kills first boot).
- Type `/help` in any chat → the help reply arrives in your Me chat.
- Type `/pending` in a busy group → progress pulses, then the open-loops ledger,
  in your Me chat only. The group itself stays untouched.

## Updating

Push to `master` (or redeploy) — Railway rebuilds, the volume keeps pairing and
history, nothing to re-scan. Watch the first boot after a big release once.

## Troubleshooting

| symptom | fix |
|---|---|
| healthcheck failing | don't override `PORT`; `/health` is public and returns 200 before pairing |
| QR never appears | check logs for `Setup page on http://localhost:…`; confirm exactly 1 replica |
| times look wrong | set `TZ=Asia/Kolkata` (the image ships tzdata) |
| pairing lost after deploy | volume missing or mounted somewhere other than `/data` |
| locked out of setup page | set `SETUP_PASSWORD` and redeploy (or read the generated one in logs) |
| want a clean slate | setup page → **Unlink** (re-scan QR); for a full wipe, delete the volume |
| script: "Google rejected that Gemini key" | create a new key at aistudio.google.com/apikey; nothing was created on Railway yet |
| script: login never finishes (SSH / no browser) | run `railway login --browserless`, then re-run the script |
| script: stopped half-way | just re-run it in the same folder — it reuses the linked project |
| forgot the setup password | `railway variable set SETUP_PASSWORD --stdin` (it redeploys; pairing is kept) |
| Windows (no WSL) | use Option B in PowerShell (`npm i -g @railway/cli`), or Option C |
| build fails: `docker VOLUME … not supported` | Railway's builder rejects `VOLUME` — attach a Railway Volume instead (the repo's Dockerfile already does it this way) |
| build fails: `go.mod requires go >= 1.26` | the builder image must be `golang:1.26-bookworm` or newer |

<details>
<summary>Verified with Railway CLI v5 (init → deploy → live checks)</summary>

```sh
railway init --name <project>
railway add --service app
railway volume add --mount-path /data
railway variable set --service app "GEMINI_API_KEY=…" "SETUP_PASSWORD=…" "TZ=Asia/Kolkata"
railway up --service app            # builds the Dockerfile, deploys
railway domain --service app        # public URL
```

Checked live: `/health` → 200, `/` → setup page, `/setup/state` → 401 before login,
login + authed state shows `gemini_key: "valid"` and a scannable QR, deploys healthy
with the volume attached and `numReplicas = 1`.
</details>

## Publish it as a one-click template (maintainer)

The README button currently opens Railway's "deploy this repo" flow, which works
today. To make it a true one-click template (pre-filled variables + volume):

1. Deploy your own working instance first (steps above).
2. Project → **Share → Create Template** (older UI: Settings → Generate Template).
3. In the template editor:
   - Description + README: paste the first-boot steps from this file.
   - Variables: `GEMINI_API_KEY` (secret, required), `SETUP_PASSWORD` (secret),
     `TZ` default `Asia/Kolkata`.
   - Attach the `/data` volume configuration.
4. Publish, then swap the button link in `README.md` and this file from
   `railway.com/new/template?template=…` to `https://railway.com/template/<id>`.

That link is what turns "5 careful steps" into "press button, scan QR".
