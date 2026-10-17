#!/usr/bin/env python3
"""mechat.py
─────────────────
Me chat (the owner's self-chat, "Message yourself") — launch-critical resolution.

Resolution order, first match wins, then verified (never a guess):

  1. explicit MECHAT_JID (env or store/mechat.json) — must verify as the owner
  2. session-derived: own PN + LID from whatsmeow_device / whatsmeow_lid_map
  3. message-derived: freshest of the PN / LID self-chat forms in messages.db;
     falling back to the account's own PN, which is the self-chat by definition

Unresolved => fail loud: --resolve exits 2, wacmd answers are dropped with a log
line, and nothing is ever sent to a guessed chat, a group, or anyone else.
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

STORE_DIR = Path(os.getenv("STORE_DIR", "store"))
MECHAT_FILE = STORE_DIR / "mechat.json"
BRIDGE_TOKEN_FILE = STORE_DIR / "bridge_token"


def _session_db_path() -> str:
    return os.getenv("WHATSAPP_DB_PATH") or str(STORE_DIR / "whatsapp.db")


def _messages_db_path() -> str:
    return os.getenv("MESSAGES_DB_PATH") or str(STORE_DIR / "messages.db")


def _split_user(jid) -> str:
    return (jid or "").split(":")[0].split("@")[0]


def _open_ro(path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def own_identity(session_db=None):
    """Return (phone, lid, source) for this WhatsApp account."""
    try:
        con = _open_ro(session_db or _session_db_path())
        try:
            row = con.execute("SELECT jid, lid FROM whatsmeow_device LIMIT 1").fetchone()
        finally:
            con.close()
        if row:
            phone, lid = _split_user(row[0]), _split_user(row[1])
            if phone.isdigit():
                return phone, lid if lid.isdigit() else "", "session-db"
    except Exception:
        pass
    phone = os.getenv("OWNER_PHONE_NUMBER", "").strip().replace("+", "")
    if phone.isdigit():
        return phone, "", "env"
    return None, "", "not-found"


def _is_group_or_status(jid) -> bool:
    jid = jid or ""
    return jid.endswith("@g.us") or jid == "status@broadcast"


def is_owner_jid(jid, session_db=None) -> bool:
    """True when jid is the owner in PN or LID form. Groups never count."""
    if not jid or _is_group_or_status(jid):
        return False
    user = _split_user(jid)
    if not user:
        return False
    phone, lid, _src = own_identity(session_db)
    if not phone:
        return False
    if user == phone:
        return True
    if lid and user == lid:
        return True
    try:
        con = _open_ro(session_db or _session_db_path())
        try:
            row = con.execute(
                "SELECT pn FROM whatsmeow_lid_map WHERE lid LIKE ?", (f"{user}%",)
            ).fetchone()
            if row and _split_user(row[0]) == phone:
                return True
            row = con.execute(
                "SELECT lid FROM whatsmeow_lid_map WHERE pn = ? OR pn LIKE ?",
                (user, f"{user}:%"),
            ).fetchone()
            if row and lid and _split_user(row[0]) == lid:
                return True
        finally:
            con.close()
    except Exception:
        pass
    return False


def resolve_self_chat(messages_db=None, session_db=None):
    """Return (jid, how). Freshest of the PN/LID self-chat forms; own PN is the
    definitional fallback (it IS the self-chat — not a guess). An explicit
    MECHAT_JID is validated and, when invalid, fails loud — no fallback."""
    configured = os.getenv("MECHAT_JID", "").strip()
    if configured:
        if verify_mechat(configured, session_db):
            return configured, "config"
        return None, "config-invalid"
    phone, lid, src = own_identity(session_db)
    if not phone:
        return None, "not-found"
    candidates = [f"{phone}@s.whatsapp.net"]
    if lid:
        candidates.append(f"{lid}@lid")
    best = None
    try:
        con = _open_ro(messages_db or _messages_db_path())
        try:
            for jid in candidates:
                try:
                    row = con.execute(
                        "SELECT COUNT(*), MAX(timestamp) FROM messages WHERE chat_jid = ?",
                        (jid,),
                    ).fetchone()
                except Exception:
                    continue
                if row and row[0]:
                    if best is None or (row[1] or "") > (best[1] or ""):
                        best = (jid, row[1])
        finally:
            con.close()
    except Exception:
        pass
    if best:
        return best[0], f"messages:{src}"
    return candidates[0], f"definitional-pn:{src}"


def verify_mechat(jid, session_db=None) -> bool:
    """The one self-check every delivery path runs: owner self-chat, never a
    group, never status."""
    if not jid or _is_group_or_status(jid):
        return False
    return is_owner_jid(jid, session_db)


def load_persisted() -> dict:
    try:
        return json.loads(MECHAT_FILE.read_text())
    except Exception:
        return {}


def persist(jid: str, how: str, phone: str, welcomed=None) -> dict:
    data = load_persisted()
    data.update({"jid": jid, "how": how, "phone": phone or "", "resolved_at": time.time()})
    if welcomed is not None:
        data["welcomed"] = bool(welcomed)
    data.setdefault("welcomed", False)
    try:
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        MECHAT_FILE.write_text(json.dumps(data, indent=2))
    except OSError as exc:
        print(f"⚠️ mechat persist failed: {exc}")
    return data


def get_mechat_jid() -> str:
    """Delivery path: persisted resolution re-verified; re-resolve when stale or
    invalid; '' when unresolved (callers must drop the send, never guess)."""
    persisted = load_persisted()
    jid = persisted.get("jid", "")
    if jid and verify_mechat(jid):
        return jid
    jid, how = resolve_self_chat()
    phone, _lid, _src = own_identity()
    if jid and verify_mechat(jid):
        persist(jid, how, phone or "")
        return jid
    return ""


def bridge_token() -> str:
    token = os.getenv("BRIDGE_TOKEN", "").strip()
    if token:
        return token
    try:
        return BRIDGE_TOKEN_FILE.read_text().strip()
    except OSError:
        return ""


def _send_via_bridge(jid: str, text: str) -> bool:
    import requests

    url = os.getenv("WA_API_URL", "http://127.0.0.1:8090/api/send")
    headers = {}
    token = bridge_token()
    if token:
        headers["X-Bridge-Token"] = token
    try:
        resp = requests.post(url, json={"recipient": jid, "message": text},
                             headers=headers, timeout=10)
        return resp.status_code == 200
    except Exception as exc:
        print(f"❌ welcome send error: {exc}")
        return False


WELCOME_TEXT = (
    "✅ *Mosaic is connected.*\n"
    "Commands you type in any chat arrive here — nowhere else.\n"
    "Try `/help`."
)


def welcome_once() -> str:
    jid = get_mechat_jid()
    if not jid:
        return "no-mechat"
    persisted = load_persisted()
    if persisted.get("welcomed"):
        return "already-welcomed"
    if _send_via_bridge(jid, WELCOME_TEXT):
        persist(jid, persisted.get("how", "verified"), persisted.get("phone", ""),
                welcomed=True)
        return "welcomed"
    return "send-failed"


def resolve_and_persist() -> dict:
    jid, how = resolve_self_chat()
    phone, _lid, _src = own_identity()
    if not jid or not verify_mechat(jid):
        return {"ok": False, "jid": "", "how": how, "phone": phone or ""}
    data = persist(jid, how, phone or "")
    return {"ok": True, "jid": jid, "how": how, "phone": phone or "",
            "welcomed": data.get("welcomed", False)}


def main(argv=None) -> int:
    args = set(argv if argv is not None else sys.argv[1:])
    if "--resolve" in args:
        result = resolve_and_persist()
        if "--welcome" in args and result.get("ok"):
            result["welcome"] = welcome_once()
        print(json.dumps(result))
        if not result.get("ok"):
            print("❌ Me chat unresolved — no sends anywhere until this resolves.",
                  file=sys.stderr)
            return 2
        return 0
    if "--welcome" in args:
        state = welcome_once()
        print(json.dumps({"welcome": state}))
        return 0 if state != "no-mechat" else 2
    if "--show" in args:
        print(json.dumps({"persisted": load_persisted(), "resolved": get_mechat_jid()}))
        return 0
    print("usage: mechat.py [--resolve [--welcome]] | [--welcome] | [--show]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
