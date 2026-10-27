import Foundation

// Sample digest for #Preview and --render-shot. Mirrors Fixtures/top10.sample.json.

extension FocusDigest {
    static var sample: FocusDigest {
        let now = Date()
        func h(_ hours: Double) -> Date { now.addingTimeInterval(hours * 3600) }
        func item(_ rank: Int, _ title: String, _ why: String, _ chat: String,
                  _ source: FocusItem.Source, _ urgency: FocusItem.Urgency,
                  due: Date? = nil, waiting: FocusItem.WaitingOn = .you, last: Double = -2) -> FocusItem {
            FocusItem(id: "s\(rank)", rank: rank, title: title, why: why, chatName: chat,
                      chatJID: nil, source: source, urgency: urgency, due: due,
                      waitingOn: waiting, lastActivity: h(last))
        }
        return FocusDigest(
            generatedAt: h(-0.2),
            headline: "Launch is gated on pricing copy and the Acme deck.",
            items: [
                item(1, "Send Acme the Q4 deck", "They asked for it by Monday — the deal review depends on it.",
                     "Launch Squad", .deadline, .critical, due: h(-3)),
                item(2, "Lock starter pricing at ₹499", "You noted this to yourself twice; Priya is waiting on final copy.",
                     "Note to self", .selfNote, .critical, due: h(20)),
                item(3, "Book the Acme demo slot for Tue", "Rohan asked you directly this morning.",
                     "Launch Squad", .ask, .high, due: h(26), last: -10),
                item(4, "Reply to Meera on the iOS checkout redirect", "Blocking QA sign-off for Thursday's launch.",
                     "Launch Squad", .ask, .high, last: -5),
                item(5, "Draft the investor update", "Self-reminder from Sunday — monthly update is due Friday.",
                     "Note to self", .selfNote, .high, due: h(72), last: -40),
                item(6, "Confirm vendor invoice with finance", "Ankit flagged a mismatch of ₹18,400.",
                     "Finance Ops", .followUp, .normal, waiting: .them, last: -20),
                item(7, "Review Arjun's landing-page copy", "You promised feedback “by tonight” yesterday.",
                     "Web Revamp", .commitment, .normal, last: -26),
                item(8, "Share hiring scorecard for the PM role", "Panel is on Wednesday.",
                     "Hiring — PM", .deadline, .normal, due: h(44), last: -30),
                item(9, "Call the CA about advance tax", "Saved to self: “ask about Q3 installment”.",
                     "Note to self", .selfNote, .normal, last: -50),
                item(10, "Nudge Kabir for the API keys", "Waiting 3 days — integration can’t start without them.",
                     "Partner — Kabir", .followUp, .normal, waiting: .them, last: -72),
            ])
    }
}
