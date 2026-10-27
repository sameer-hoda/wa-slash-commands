import Foundation

// FocusDigest — the ONLY contract between the LLM back end and the UI.
// The back end (Gemini over non-archived, work-related chats) writes this
// JSON; the UI never sees raw chats. Schema lives in SPEC.md §6.

struct FocusDigest: Codable, Equatable {
    var generatedAt: Date
    /// One editorial line, ≤ 90 chars. e.g. "Launch is gated on pricing copy and the Acme deck."
    var headline: String
    var items: [FocusItem]

    static let empty = FocusDigest(generatedAt: .distantPast, headline: "", items: [])

    enum CodingKeys: String, CodingKey {
        case generatedAt = "generated_at", headline, items
    }
}

struct FocusItem: Codable, Identifiable, Equatable, Hashable {
    var id: String               // stable across refreshes (hash of chat + topic) — drives animations
    var rank: Int                // 1…10
    var title: String            // ≤ 60 chars, imperative: "Send Acme the Q4 deck"
    var why: String              // ≤ 100 chars: why it matters / what's blocked
    var chatName: String         // "Launch Squad", or "Note to self"
    var chatJID: String?         // for "Open in WhatsApp"
    var source: Source
    var urgency: Urgency
    var due: Date?               // explicit or inferred deadline
    var waitingOn: WaitingOn     // whose move it is
    var lastActivity: Date?      // newest message that fed this item

    enum Source: String, Codable { case selfNote = "self_note", ask, commitment, deadline, followUp = "follow_up" }
    enum Urgency: String, Codable { case critical, high, normal }
    enum WaitingOn: String, Codable { case you, them }

    enum CodingKeys: String, CodingKey {
        case id, rank, title, why, source, urgency, due
        case chatName = "chat_name", chatJID = "chat_jid"
        case waitingOn = "waiting_on", lastActivity = "last_activity"
    }

    /// Visual tone: self-notes are always teal (the user's own voice),
    /// otherwise urgency decides.
    var tone: Mosaic.Tone {
        if source == .selfNote { return .selfNote }
        switch urgency {
        case .critical: return .critical
        case .high:     return .high
        case .normal:   return .normal
        }
    }

    var isOverdue: Bool { (due.map { $0 < Date() }) ?? false }
}

extension JSONDecoder {
    static let focus: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .custom { dec in
            let s = try dec.singleValueContainer().decode(String.self)
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = f.date(from: s) { return date }
            f.formatOptions = [.withInternetDateTime]
            if let date = f.date(from: s) { return date }
            f.formatOptions = [.withFullDate]
            if let date = f.date(from: s) { return date }
            throw DecodingError.dataCorrupted(.init(codingPath: dec.codingPath,
                                                    debugDescription: "Bad date \(s)"))
        }
        return d
    }()
}
