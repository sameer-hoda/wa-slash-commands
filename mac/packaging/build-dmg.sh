#!/usr/bin/env bash
# build-dmg.sh — package Mosaic.app into a signed, notarized DMG (spec v2 §10).
#
# Required env: APPLE_ID, APPLE_TEAM_ID, APP_PASSWORD (notarytool keychain or
# --password), SPARKLE_ED_KEY (private key for appcast signing, kept offline).
set -euo pipefail
APP="${1:-build/Mosaic.app}"
DMG="${2:-dist/Mosaic.dmg}"
VOLNAME="Mosaic"

if [[ -z "${APPLE_ID:-}" || -z "${APPLE_TEAM_ID:-}" ]]; then
	echo "error: set APPLE_ID and APPLE_TEAM_ID" >&2
	exit 2
fi
if [[ ! -d "$APP" ]]; then
	echo "error: app bundle not found: $APP" >&2
	exit 2
fi

# Sign every Mach-O binary inside the bundle before sealing (spec v2 trap:
# unsigned .so/.dylib breaks the signature and fails notarization).
/usr/bin/codesign --sign "Developer ID Application" --options runtime \
	--entitlements mac/packaging/Mosaic.entitlements \
	--timestamp --force "$APP"
/usr/bin/codesign --verify --deep --strict "$APP"
/usr/bin/spctl -a -vvv --type execute "$APP"

rm -f "$DMG"
/usr/bin/hdiutil create -volname "$VOLNAME" -srcfolder "$APP" -ov -format UDZO "$DMG"
xcrun notarytool submit "$DMG" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" --wait
xcrun stapler staple "$DMG"
/usr/bin/spctl -a -vvv --type open --context context:primary-signature "$DMG" || true
echo "DMG ready: $DMG"
