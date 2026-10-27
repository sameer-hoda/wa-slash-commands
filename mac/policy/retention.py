"""Sleep/wake + retention policy helpers (spec v2 §8)."""

SLEEP_ANSWER_CUTOFF_SECONDS = 600
RETENTION_CHOICES = {30, 90, -1}  # -1 means forever


def stale_action(age_seconds: int) -> str:
    if age_seconds < SLEEP_ANSWER_CUTOFF_SECONDS:
        return "answer"
    return "skipped-asleep"


def retention_cutoff(days: int) -> int:
    if days not in RETENTION_CHOICES:
        raise ValueError(f"retention must be one of {sorted(RETENTION_CHOICES)}")
    return days
