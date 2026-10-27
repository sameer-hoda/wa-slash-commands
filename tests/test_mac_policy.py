import pytest

from mac.policy.retention import retention_cutoff, stale_action


def test_old_command_skipped():
    assert stale_action(11 * 60) == "skipped-asleep"


def test_fresh_command_answered():
    assert stale_action(60) == "answer"


def test_retention_rejects_unknown():
    with pytest.raises(ValueError):
        retention_cutoff(45)


def test_retention_accepts_known():
    assert retention_cutoff(30) == 30
    assert retention_cutoff(90) == 90
    assert retention_cutoff(-1) == -1
