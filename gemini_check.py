#!/usr/bin/env python3
"""gemini_check.py — prints one of: valid | invalid | missing (stdout)."""

import os
import sys

_dir = os.path.dirname(os.path.abspath(__file__))
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_dir, ".env"))
except Exception:
    pass


def main() -> int:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        try:
            from engine import GEMINI_API_KEY as engine_key

            key = (engine_key or "").strip()
        except Exception:
            key = ""
    if not key:
        print("missing")
        return 1
    try:
        import google.generativeai as genai

        genai.configure(api_key=key)
        iterator = genai.list_models()
        next(iter(iterator))
        print("valid")
        return 0
    except Exception as exc:
        print("invalid")
        print(str(exc)[:200], file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
