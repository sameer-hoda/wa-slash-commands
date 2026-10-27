#!/usr/bin/env bash
# snap.sh — snapshot check (BAMA build-and-verify analog).
# Renders the real UI offscreen to PNG: one shot against the live app state,
# one against an isolated bridge with throwaway data (fresh onboarding).
# A UI change is only "done" when a human has seen both images.
set -euo pipefail
cd "$(dirname "$0")"
APP="../../build/Mosaic.app"
BIN="$APP/Contents/MacOS/Mosaic"
OUT="${1:-/tmp/Mosaic-shots}"
if [[ ! -x "$BIN" ]]; then echo "run ./build.sh first" >&2; exit 2; fi
mkdir -p "$OUT"
rm -f "$OUT"/*.png

shot() {
  # $1 = extra env assignments, $2 = output png (real window pixels)
  env $1 "$BIN" --render-shot "$2"
}

echo "==> live-state shot (your real pairing)"
shot "" "$OUT/live.png"

echo "==> fresh-onboarding shot (isolated bridge, throwaway data)"
SHOTDIR=/tmp/mosaic-shot-data
rm -rf "$SHOTDIR" && mkdir -p "$SHOTDIR"
STORE_DIR="$SHOTDIR" PORT=18081 SETUP_NO_AUTH=1 \
  PY_SCRIPTS_DIR="$APP/Contents/Resources/python" \
  "$APP/Contents/Resources/wa-bridge" >/tmp/mosaic-shot-bridge.log 2>&1 &
BRIDGE_PID=$!
cleanup() { kill "$BRIDGE_PID" 2>/dev/null || true; }
trap cleanup EXIT
for i in $(seq 1 20); do
  if curl -sf -o /dev/null "http://127.0.0.1:18081/health"; then break; fi
  sleep 1
done
curl -sf -o /dev/null "http://127.0.0.1:18081/health" \
  || { echo "isolated bridge never came up; see /tmp/mosaic-shot-bridge.log" >&2; exit 1; }
shot "MOSAIC_SETUP_URL=http://127.0.0.1:18081 MOSAIC_SUPPORT_DIR=$SHOTDIR" "$OUT/fresh.png"

echo "==> focus shot (sample digest, no bridge)"
"$BIN" --render-shot-focus "$OUT/focus.png"

echo "SNAPSHOT done $OUT"
ls -l "$OUT"
