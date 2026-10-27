"""Mac IPC event protocol: JSON lines over a Unix socket."""

import json
import os

SOCKET_MODE = 0o600
SOCKET_NAME = "bridge.sock"

EVENT_TYPES = {
    "qr",
    "scanned",
    "connected",
    "logged_out",
    "heartbeat",
    "command",
    "answer",
}


def socket_path(app_support: str) -> str:
    return os.path.join(app_support, SOCKET_NAME)


def encode_event(type: str, payload: dict) -> str:
    if type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {type}")
    return json.dumps({"type": type, "payload": payload or {}})


def decode_event(line: str) -> dict:
    data = json.loads(line.strip())
    if "type" not in data or "payload" not in data:
        raise ValueError("event must have type and payload")
    if data["type"] not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {data['type']}")
    return data
