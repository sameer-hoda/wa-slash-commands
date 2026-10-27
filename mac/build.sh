#!/usr/bin/env bash
# build.sh — one-command Mosaic build (BAMA-style pipeline).
#
#   ./build.sh            release build -> ../build/Mosaic.app, ad-hoc signed
#   ./build.sh --debug    faster unoptimized build (app still assembles + signs)
#   ./build.sh --install  also copy the bundle to ~/Applications/Mosaic.app
#   ./build.sh --dmg      also produce ../dist/Mosaic.dmg (ad-hoc signed,
#                         shareable; Gatekeeper needs right-click > Open until
#                         Developer-ID signing + notarization are configured)
#
# Never build the app by hand with swiftc: this script is the only supported
# path, so every bundle on every machine has identical contents.
set -euo pipefail
cd "$(dirname "$0")"
REPO=".."
BUILD="$REPO/build"
APP="$BUILD/Mosaic.app"
CONFIG=release
INSTALL=0
DMG=0
for arg in "$@"; do
  case "$arg" in
    --debug) CONFIG=debug ;;
    --install) INSTALL=1 ;;
    --dmg) DMG=1 ;;
    *) echo "usage: ./build.sh [--debug] [--install] [--dmg]" >&2; exit 2 ;;
  esac
done

echo "==> swift build ($CONFIG)"
# Strip the builder's home dir from the shipped binary: no personal paths
# in a shareable DMG. Crash logs still show MOSAIC/-rooted source paths.
REPO_ABS="$(cd "$REPO" && pwd)"
swift build -c "$CONFIG" --scratch-path "$BUILD/swift-scratch" \
  -Xswiftc -file-prefix-map -Xswiftc "$REPO_ABS/=MOSAIC/" \
  -Xswiftc -debug-prefix-map -Xswiftc "$REPO_ABS/=MOSAIC/"

echo "==> go bridge"
mkdir -p "$BUILD/.gocache" "$BUILD/.tmpcgo"
GOCACHE_DIR="$(pwd)/$BUILD/.gocache"
GOTMP_DIR="$(pwd)/$BUILD/.tmpcgo"
env GOCACHE="$GOCACHE_DIR" GOTMPDIR="$GOTMP_DIR" TMPDIR="$GOTMP_DIR" \
  go -C "$REPO/bridge" build -trimpath -o wa-bridge-local .
mv "$REPO/bridge/wa-bridge-local" "$BUILD/wa-bridge"

echo "==> python runtime (bundled, no tester installs)"
RT="$BUILD/python-runtime"
if [[ ! -x "$RT/bin/python3" ]]; then
  mkdir -p "$BUILD/python-dl"
  TARBALL="$BUILD/python-dl/py.tar.gz"
  if [[ ! -f "$TARBALL" ]]; then
    echo "    fetching python-build-standalone 3.12 (aarch64)…"
    curl -fL -o "$TARBALL" \
      "https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.12.7%2B20241016-aarch64-apple-darwin-install_only.tar.gz"
  fi
  rm -rf "$RT" && mkdir -p "$RT"
  tar -xzf "$TARBALL" -C "$RT"
  "$RT/bin/python3" -m pip install --quiet -r "$REPO/requirements.txt"
fi
"$RT/bin/python3" -c "import google.generativeai, dotenv; print('    runtime deps ok')"

echo "==> assemble bundle"
BIN="$BUILD/swift-scratch/$CONFIG/Mosaic"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/python"
/usr/bin/plutil -lint packaging/Mosaic-Info.plist
cp "$BIN" "$APP/Contents/MacOS/Mosaic"
/usr/bin/strip -S "$APP/Contents/MacOS/Mosaic"
cp packaging/Mosaic-Info.plist "$APP/Contents/Info.plist"
cp packaging/Mosaic.icns "$APP/Contents/Resources/Mosaic.icns"
cp packaging/TESTERS.txt "$APP/Contents/Resources/TESTERS.txt" 2>/dev/null || true
cp "$BUILD/wa-bridge" "$APP/Contents/Resources/wa-bridge"
cp "$REPO/wacmd.py" "$REPO/engine.py" "$REPO/formatter.py" "$REPO/ledger.py" \
   "$REPO/mechat.py" "$REPO/scripts/gemini_check.py" "$REPO/requirements.txt" \
   "$APP/Contents/Resources/python/"
rm -rf "$APP/Contents/Resources/python-runtime"
cp -R "$RT" "$APP/Contents/Resources/python-runtime"
/usr/bin/codesign --sign - --force --deep --options runtime "$APP"
/usr/bin/codesign --verify --deep --strict "$APP"
echo "    bundle ok: $APP ($(du -sh "$APP" | cut -f1))"

if [[ "$INSTALL" == 1 ]]; then
  echo "==> install"
  rm -rf ~/Applications/Mosaic.app
  mkdir -p ~/Applications
  cp -R "$APP" ~/Applications/Mosaic.app
  echo "    installed: ~/Applications/Mosaic.app"
fi

if [[ "$DMG" == 1 ]]; then
  echo "==> dmg (drag-install: Mosaic.app + Applications alias)"
  mkdir -p "$REPO/dist"
  DMG_OUT="$REPO/dist/Mosaic.dmg"
  rm -f "$DMG_OUT"
  STAGE="$BUILD/dmg-stage"
  rm -rf "$STAGE"
  mkdir -p "$STAGE"
  cp -R "$APP" "$STAGE/Mosaic.app"
  ln -s /Applications "$STAGE/Applications"
  /usr/bin/hdiutil create -volname "Mosaic" -srcfolder "$STAGE" -ov -format UDZO "$DMG_OUT"
  rm -rf "$STAGE"
  echo "    dmg: $DMG_OUT ($(du -h "$DMG_OUT" | cut -f1))"
fi

echo "ALL DONE — next: mac/tools/snap.sh (snapshot check) before calling it done."
