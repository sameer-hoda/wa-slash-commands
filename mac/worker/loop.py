"""Long-lived Python worker: loop guard + dedupe + command check."""


def is_command(text: str) -> bool:
    return bool(text) and text.lstrip().startswith("/")


def should_handle(sender_jid: str, message_id: str, seen: set,
                   is_own: bool = False) -> bool:
    if is_own:
        return False
    if not sender_jid or not message_id:
        return False
    if message_id in seen:
        return False
    return True
