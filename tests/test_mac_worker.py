from mac.worker.loop import is_command, should_handle


def test_own_mechat_message_never_handled():
    assert should_handle("owner@s.whatsapp.net", "m1", set(), is_own=True) is False


def test_duplicate_message_id_ignored():
    assert should_handle("a@s.whatsapp.net", "m1", {"m1"}) is False


def test_fresh_command_from_other_is_handled():
    assert should_handle("a@s.whatsapp.net", "m2", {"m1"}, is_own=False) is True


def test_only_slash_text_is_command():
    assert is_command("/help") is True
    assert is_command("hello") is False
    assert is_command("") is False
