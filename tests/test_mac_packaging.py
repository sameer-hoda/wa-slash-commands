import plistlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INFO = REPO / "mac" / "packaging" / "Mosaic-Info.plist"
ENTITLEMENTS = REPO / "mac" / "packaging" / "Mosaic.entitlements"
DMG_SCRIPT = REPO / "mac" / "packaging" / "build-dmg.sh"
APPCAST = REPO / "mac" / "Updates" / "appcast.xml"


def test_info_plist_bundle_identity():
    with INFO.open("rb") as f:
        info = plistlib.load(f)
    assert info["CFBundleIdentifier"] == "com.sameerhoda.mosaic"
    # Proper app: dock icon + menu bar + window (LSUIElement hides all that).
    assert info["LSUIElement"] is False
    assert "SUFeedURL" in info


def test_entitlements_parses():
    with ENTITLEMENTS.open("rb") as f:
        ent = plistlib.load(f)
    assert isinstance(ent, dict)


def test_dmg_script_gates_signing_and_notarization():
    text = DMG_SCRIPT.read_text()
    assert "codesign --verify --deep --strict" in text
    assert "spctl -a" in text
    assert "notarytool" in text
    assert "stapler staple" in text


def test_appcast_has_ed_signature_slot():
    text = APPCAST.read_text()
    assert "sparkle:edSignature" in text
