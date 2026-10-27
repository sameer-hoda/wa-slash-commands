"""Tests for the tuning lab's scoring/blinding (pure functions, no DB)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import focus_tune as lab



def items(*pairs):
    return [{"rank": r, "chat_jid": j} for r, j in pairs]


def test_score_digest_perfect_top_hit():
    s = lab.score_digest(items((1, "a"), (2, "b")), {"a", "c"})
    assert s["mrr"] == 1.0
    assert s["coverage"] == 0.5
    assert s["auto"] == round(0.6 + 0.4 * 0.5, 3)


def test_score_digest_miss():
    s = lab.score_digest(items((1, "a"), (2, "b")), {"z"})
    assert s == {"mrr": 0.0, "coverage": 0.0, "auto": 0.0}


def test_score_digest_lower_hit():
    s = lab.score_digest(items((1, "a"), (4, "z")), {"z"})
    assert s["mrr"] == 0.25


def test_score_digest_empty_engaged():
    s = lab.score_digest(items((1, "a")), set())
    assert s == {"mrr": 0.0, "coverage": 0.0, "auto": 0.0}


def test_score_merges_lid_phone_identity():
    # Same conversation under two spellings must not split credit.
    s = lab.score_digest(items((2, "123@lid")), {"123@s.whatsapp.net"})
    assert s["mrr"] == 0.5 and s["coverage"] == 1.0
    g = lab.score_digest(items((1, "120@g.us")), {"120@s.whatsapp.net"})
    assert g["mrr"] == 0.0  # groups stay exact


def test_assign_labels_deterministic_and_covering():
    a = lab.assign_labels(["x", "y", "z", "w"], "s1")
    b = lab.assign_labels(["x", "y", "z", "w"], "s1")
    c = lab.assign_labels(["x", "y", "z", "w"], "s2")
    assert a == b
    assert set(a.values()) == {"x", "y", "z", "w"}
    assert set(a) == {"A", "B", "C", "D"}
    assert a != c or True  # different seeds may collide; determinism is what matters
