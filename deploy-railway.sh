#!/usr/bin/env bash
# deploy-railway.sh — deploy Mosaic (wa-slash-commands) to Railway in one go.
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/sameer-hoda/wa-slash-commands/master/deploy-railway.sh)
#
# or, from a clone of the repo:   ./deploy-railway.sh
#
# It asks for two things (Gemini key, setup password), then:
#   installs the Railway CLI if needed → logs you in → creates a project and a
#   service → attaches the /data volume → sets variables → builds and deploys →
#   gives the service a public URL → waits until it is healthy → opens the setup
#   page so you can scan the WhatsApp QR.
#
# Safe to re-run: an already-linked project is reused, and only the variables
# and code are updated (your WhatsApp pairing on the volume is kept).
#
# Optional environment overrides:
#   PROJECT_NAME   (default: wa-slash-commands)
#   SERVICE_NAME   (default: mosaic)
#   TZ_VALUE       (default: Asia/Kolkata)
#   GEMINI_API_KEY / SETUP_PASSWORD  — skip the prompts (for scripting)

set -euo pipefail

REPO_URL="https://github.com/sameer-hoda/wa-slash-commands"
PROJECT_NAME="${PROJECT_NAME:-wa-slash-commands}"
SERVICE_NAME="${SERVICE_NAME:-mosaic}"
TZ_VALUE="${TZ_VALUE:-Asia/Kolkata}"

# ── output helpers ────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  B=$'\033[1m'; D=$'\033[2m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; C=$'\033[36m'; N=$'\033[0m'
else
  B=""; D=""; G=""; Y=""; R=""; C=""; N=""
fi
STEP=0
step() { STEP=$((STEP + 1)); printf "\n%s[%d/9]%s %s%s%s\n" "$C" "$STEP" "$N" "$B" "$1" "$N"; }
ok()   { printf "  %s✓%s %s\n" "$G" "$N" "$1"; }
warn() { printf "  %s!%s %s\n" "$Y" "$N" "$1"; }
die()  { printf "\n  %s✗ %s%s\n\n" "$R" "$1" "$N" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed."; }

open_url() {
  if command -v open >/dev/null 2>&1; then open "$1" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1 || true
  fi
}

printf "\n%s📱 Mosaic → Railway%s  %sone container · one volume · ~5 minutes%s\n" "$B" "$N" "$D" "$N"

need curl
need git

# ── 1. get the code ───────────────────────────────────────────────────────────
step "Getting the code"
if [ -f railway.toml ] && [ -f Dockerfile ] && grep -q "Mosaic" railway.toml 2>/dev/null; then
  ok "Using this folder: $(pwd)"
else
  DEST="${HOME}/wa-slash-commands"
  if [ -d "$DEST/.git" ]; then
    git -C "$DEST" pull --ff-only -q || warn "Could not update $DEST — deploying it as is"
  else
    git clone -q --depth 1 "$REPO_URL" "$DEST"
  fi
  cd "$DEST"
  ok "Code is in $DEST"
fi

# ── 2. Railway CLI ────────────────────────────────────────────────────────────
step "Railway CLI"
export PATH="$HOME/.railway/bin:$PATH"
if ! command -v railway >/dev/null 2>&1; then
  printf "  Installing the Railway CLI…\n"
  bash <(curl -fsSL https://railway.com/install.sh) -y >/dev/null
  command -v railway >/dev/null 2>&1 || die "Install failed. Install manually: https://docs.railway.com/cli (brew install railway / npm i -g @railway/cli)"
fi
ok "$(railway --version 2>/dev/null | head -1)"

# ── 3. login ──────────────────────────────────────────────────────────────────
step "Railway account"
if ! railway whoami >/dev/null 2>&1; then
  printf "  A browser window will open — sign in or create a free Railway account.\n"
  railway login || die "Login did not complete. Run: railway login"
fi
ok "$(railway whoami 2>/dev/null | tail -1)"

# ── 4. ask the two questions ──────────────────────────────────────────────────
step "Your settings"
if [ -z "${GEMINI_API_KEY:-}" ]; then
  printf "  Get a key at %shttps://aistudio.google.com/apikey%s (use a billing-enabled project).\n" "$C" "$N"
  while :; do
    read -rsp "  Gemini API key (hidden): " GEMINI_API_KEY; echo
    GEMINI_API_KEY="$(printf %s "$GEMINI_API_KEY" | tr -d '[:space:]')"
    [ -n "$GEMINI_API_KEY" ] && break
    warn "The key can't be empty."
  done
fi
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
  -H "x-goog-api-key: ${GEMINI_API_KEY}" \
  "https://generativelanguage.googleapis.com/v1beta/models" || true)"
code="${code:-000}"
case "$code" in
  200) ok "Gemini key works" ;;
  000) warn "Couldn't reach Google to check the key — continuing" ;;
  *)   die "Google rejected that Gemini key (HTTP $code). Check it at https://aistudio.google.com/apikey and re-run." ;;
esac

GENERATED_PW=0
if [ -z "${SETUP_PASSWORD:-}" ]; then
  printf "  Choose a password for your setup page (leave empty to generate one).\n"
  while :; do
    read -rsp "  Setup password (hidden): " SETUP_PASSWORD; echo
    if [ -z "$SETUP_PASSWORD" ]; then
      SETUP_PASSWORD="$(LC_ALL=C tr -dc 'a-km-np-z2-9' </dev/urandom | head -c 12 || true)"
      GENERATED_PW=1
      break
    fi
    [ "${#SETUP_PASSWORD}" -ge 8 ] || { warn "Use at least 8 characters."; continue; }
    read -rsp "  Confirm password: " confirm; echo
    [ "$confirm" = "$SETUP_PASSWORD" ] && break
    warn "Passwords didn't match — try again."
  done
fi
ok "Password set"

# ── 5. project + service ──────────────────────────────────────────────────────
step "Project and service"
FRESH=1
if railway status >/dev/null 2>&1; then
  printf "  This folder is already linked to a Railway project:\n"
  railway status 2>/dev/null | sed 's/^/    /'
  read -rp "  Update that deployment? [Y/n] " ans
  case "${ans:-y}" in
    [nN]*) railway unlink -y >/dev/null 2>&1 || railway unlink >/dev/null 2>&1 || true ;;
    *) FRESH=0 ;;
  esac
fi
if [ "$FRESH" = 1 ]; then
  railway init --name "$PROJECT_NAME" >/dev/null || die "Couldn't create the project."
  ok "Created project '$PROJECT_NAME'"
  railway add --service "$SERVICE_NAME" >/dev/null || die "Couldn't create the service."
  ok "Created service '$SERVICE_NAME'"
else
  ok "Reusing the linked project"
fi
if railway service "$SERVICE_NAME" >/dev/null 2>&1; then
  ok "Linked service '$SERVICE_NAME'"
elif [ "$FRESH" = 0 ]; then
  warn "No service called '$SERVICE_NAME' — keeping the service this folder is already linked to"
else
  die "Couldn't link service '$SERVICE_NAME'. Run: railway service"
fi

# ── 6. volume ─────────────────────────────────────────────────────────────────
step "Storage volume (keeps your WhatsApp login across deploys)"
if railway volume list 2>/dev/null | grep -q "/data"; then
  ok "Volume at /data already attached"
else
  railway volume add --mount-path /data >/dev/null || die "Couldn't create the volume. Add it in the dashboard: Service → Settings → Volumes → mount path /data"
  ok "Volume attached at /data"
fi

# ── 7. variables (secrets go through stdin, never the command line) ───────────
step "Variables"
printf %s "$GEMINI_API_KEY" | railway variable set GEMINI_API_KEY --stdin --skip-deploys >/dev/null
printf %s "$SETUP_PASSWORD" | railway variable set SETUP_PASSWORD --stdin --skip-deploys >/dev/null
railway variable set "TZ=$TZ_VALUE" --skip-deploys >/dev/null
ok "GEMINI_API_KEY, SETUP_PASSWORD, TZ=$TZ_VALUE"

# ── 8. build + deploy ─────────────────────────────────────────────────────────
step "Building and deploying (first build takes 3–6 minutes)"
railway up --detach -y || die "The deploy couldn't start. Run: railway up --ci  and check the log."
ok "Build started (the next step waits for it)"

DOMAIN_OUT="$(railway domain 2>&1 || true)"
URL="$(printf %s "$DOMAIN_OUT" | grep -oE 'https?://[A-Za-z0-9.-]+\.up\.railway\.app' | head -1)"
[ -n "$URL" ] || URL="$(printf %s "$DOMAIN_OUT" | grep -oE '[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.up\.railway\.app' | head -1)"
[ -n "$URL" ] || URL="$(railway domain list 2>/dev/null | grep -oE '[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.up\.railway\.app' | head -1)"
[ -n "$URL" ] || die "Couldn't get a public URL. Dashboard → Service → Settings → Networking → Generate Domain."
case "$URL" in http*) ;; *) URL="https://$URL" ;; esac
ok "Public URL: $URL"

# ── 9. wait for health ────────────────────────────────────────────────────────
step "Waiting for Mosaic to start"
healthy=0
for _ in $(seq 1 90); do
  if curl -fsS --max-time 5 "$URL/health" >/dev/null 2>&1; then healthy=1; break; fi
  printf "."; sleep 5
done
echo
if [ "$healthy" = 1 ]; then ok "Healthy"; else warn "Not answering yet (new URLs can take a minute) — check: railway logs"; fi

# ── done ──────────────────────────────────────────────────────────────────────
printf "\n%s✅ Mosaic is running.%s Last step — link your WhatsApp:\n\n" "$G$B" "$N"
printf "  1. Open   %s%s%s\n" "$C" "$URL" "$N"
if [ "$GENERATED_PW" = 1 ]; then
  printf "  2. Log in with password   %s%s%s   %s(save it — you'll need it again)%s\n" "$B" "$SETUP_PASSWORD" "$N" "$D" "$N"
else
  printf "  2. Log in with the password you chose\n"
fi
printf "  3. On your phone: WhatsApp → Settings → Linked devices → Link a device → scan the QR\n"
printf "  4. Wait for %s\"Connected as +91…\"%s — a welcome message lands in your Me chat\n" "$B" "$N"
printf "\n  Then type %s/pending%s in any group. Answers arrive only in your Me chat.\n" "$B" "$N"
printf "\n  %sUseful later:  railway logs · railway open · re-run this script to update%s\n\n" "$D" "$N"

open_url "$URL"
