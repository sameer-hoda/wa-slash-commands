#!/usr/bin/env python3
"""Generate the Mosaic app icon (v2) with Nano Banana.

Style reference from the user: geometric star-tile mosaic — deep teal
triangles, ivory/cream star medallions, burnt-terracotta accents, subtle
stone texture. Single bold medallion so it reads at 16px.
Reads GEMINI_API_KEY from the project .env (never printed).
"""
import base64
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_key():
    for path in (os.path.join(ROOT, ".env"), os.path.join(os.getcwd(), ".env")):
        try:
            with open(path) as f:
                m = re.search(r'GEMINI_API_KEY\s*=\s*"?([^"\s#]+)"?', f.read())
                if m and not m.group(1).lower().startswith("your_"):
                    return m.group(1)
        except OSError:
            pass
    return os.getenv("GEMINI_API_KEY", "").strip()


PROMPT = (
    "macOS app icon, rounded square tile. A single bold geometric eight-point "
    "star medallion in the center, mosaic tile style: deep teal (#0f4c4c) "
    "triangular facets, warm ivory-cream (#f2ead8) star points with a subtle "
    "marble stone texture, burnt terracotta (#c96f3b) diamond accents at the "
    "diagonal corners. Dark espresso-brown background (#171310) with a thin "
    "rounded border. Flat vector look with crisp edges, perfectly symmetric, "
    "high contrast, no text, no letters, no shadows outside the icon, "
    "readable as a tiny 16-pixel glyph, professional Apple design award "
    "aesthetic"
)


def main():
    key = load_key()
    if not key:
        print("no key", file=sys.stderr)
        return 2
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           "gemini-2.5-flash-image:generateContent?key=" + key)
    body = json.dumps({
        "contents": [{"parts": [{"text": PROMPT}]}],
        "generationConfig": {"responseModalities": ["IMAGE"],
                             "imageConfig": {"aspectRatio": "1:1"}},
    }).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
    except Exception as exc:
        print(f"request failed: {exc}"[:300], file=sys.stderr)
        return 1
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            blob = part.get("inlineData", {})
            if blob.get("data"):
                out = os.path.join(ROOT, "assets", "icon-1024.png")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "wb") as f:
                    f.write(base64.b64decode(blob["data"]))
                print(f"wrote {out}")
                return 0
    print("no image in response", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
