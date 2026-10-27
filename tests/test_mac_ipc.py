from mac.ipc.protocol import decode_event, encode_event


def test_encode_decode_qr_event_roundtrip():
    line = encode_event("qr", {"data_url": "x", "expires_in": 20})
    assert decode_event(line) == {
        "type": "qr",
        "payload": {"data_url": "x", "expires_in": 20},
    }


def test_socket_path_lives_under_app_support():
    from mac.ipc.protocol import socket_path

    assert socket_path("/tmp/Mosaic").endswith("bridge.sock")
    assert socket_path("/tmp/Mosaic").startswith("/tmp/Mosaic")


def test_socket_mode_is_owner_only():
    from mac.ipc.protocol import SOCKET_MODE

    assert SOCKET_MODE == 0o600
