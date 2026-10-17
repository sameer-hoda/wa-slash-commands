from formatter import fmt_pending, fmt_recap, fmt_sotu, fmt_stats

SOTU_FIXTURE = {
    "group_purpose": "Acme launch coordination",
    "big_picture_objective": "Ship v1 by end of October",
    "key_themes": [
        {"title": "Landing page", "description": "Design approved v3"},
        {"title": "Legal", "description": "Review pending"},
    ],
    "recent_happenings": "Launch moved to 22 Oct.",
    "key_ask": "Priya needs the signed SOW",
}

SOTU_GOLDEN = (
    "*State of the Union*\n"
    "\n"
    "*What this group is about*\n"
    "Acme launch coordination\n"
    "\n"
    "*The big picture objective*\n"
    "Ship v1 by end of October\n"
    "\n"
    "*Key discussion themes*\n"
    "• *Landing page* — Design approved v3\n"
    "• *Legal* — Review pending\n"
    "\n"
    "*What's been happening recently*\n"
    "Launch moved to 22 Oct.\n"
    "\n"
    "*The one thing asked for recently*\n"
    "Priya needs the signed SOW"
)

PENDING_FIXTURE = {
    "initiatives": [
        {"title": "Vendor selection", "updates": ["14 Oct — Rahul: shortlist done"],
         "next_steps": "Rahul to confirm SLA"},
        {"title": "SOW", "updates": ["13 Oct — Priya: sent draft"],
         "next_steps": "Owner to sign"},
    ]
}

PENDING_GOLDEN = (
    "🎯 Vendor selection\n"
    "\n"
    "📅 14 Oct — Rahul: shortlist done\n"
    "\n"
    "⏭ *Next:* Rahul to confirm SLA\n"
    "\n"
    "────────────────────\n"
    "\n"
    "🎯 SOW\n"
    "\n"
    "📅 13 Oct — Priya: sent draft\n"
    "\n"
    "⏭ *Next:* Owner to sign"
)

STATS_FIXTURE = {
    "participants": [
        {"name": "Priya", "message_count": 120, "share_pct": 42.0,
         "role_tag": "The Driver", "one_liner": "keeps everyone moving"},
        {"name": "Rahul", "message_count": 80, "share_pct": 28.0,
         "role_tag": "The Reviewer", "one_liner": "asks the hard questions"},
    ],
    "group_health": "Active",
    "bottleneck": "None",
}

STATS_GOLDEN = (
    "📊 *Team Stats — Last 14 Days*\n"
    "\n"
    "👤 *Priya* (120 msgs, 42%) — The Driver\n"
    "👤 *Rahul* (80 msgs, 28%) — The Reviewer\n"
    "\n"
    "🌡️ Group Health: *Active*"
)

RECAP_FIXTURE = {
    "date_str": "16 Oct 2026",
    "events": [
        {"time": "3:49 PM", "actor": "Meera", "action": "approved landing v3"},
        {"time": "5:10 PM", "actor": "Priya", "action": "asked for signed SOW"},
    ],
    "summary": "Design approved; SOW still pending.",
}

RECAP_GOLDEN = (
    "📋 *Last 24 Hrs*\n"
    "16 Oct 2026\n"
    "\n"
    "🕒 3:49 PM · *Meera* — approved landing v3\n"
    "🕒 5:10 PM · *Priya* — asked for signed SOW\n"
    "\n"
    "🔍 *Summary:* Design approved; SOW still pending."
)


def test_fmt_sotu_golden():
    assert fmt_sotu(SOTU_FIXTURE) == SOTU_GOLDEN


def test_fmt_pending_golden():
    assert fmt_pending(PENDING_FIXTURE) == PENDING_GOLDEN


def test_fmt_stats_golden():
    assert fmt_stats(STATS_FIXTURE, 14) == STATS_GOLDEN


def test_fmt_recap_golden():
    assert fmt_recap(RECAP_FIXTURE) == RECAP_GOLDEN


def test_fmt_pending_empty():
    assert fmt_pending({"initiatives": []}) == "✅ *No critical open loops found.*"


def test_fmt_recap_empty():
    assert fmt_recap({"events": [], "summary": "Analysis failed.", "date_str": ""}) == (
        "📌 *24h Recap*\n\n_No significant events in the last 24 hours._"
    )


def test_titles_name_the_chat():
    assert fmt_sotu(SOTU_FIXTURE, chat_name="Launch Squad").startswith(
        "*State of the Union — Launch Squad*")
    assert "*Team Stats — Last 14 Days — Launch Squad*" in fmt_stats(
        STATS_FIXTURE, 14, chat_name="Launch Squad")
    assert fmt_recap(RECAP_FIXTURE, chat_name="Launch Squad").startswith(
        "📋 *Last 24 Hrs — Launch Squad*")
    assert fmt_recap({"events": [], "summary": "s", "date_str": ""},
                     chat_name="Launch Squad").startswith("📌 *24h Recap — Launch Squad*")


def test_titles_skip_raw_jid_labels():
    assert fmt_sotu(SOTU_FIXTURE, chat_name="910x@lid").startswith("*State of the Union*")
    assert "Team Stats — Last 14 Days*" in fmt_stats(STATS_FIXTURE, 14, chat_name="910x@lid")
    assert fmt_recap(RECAP_FIXTURE, chat_name="910x@lid").startswith("📋 *Last 24 Hrs*")
