import SwiftUI
import AppKit

// Small building blocks shared by the popover and the window.

// MARK: - Header

struct FocusHeader: View {
    let digest: FocusDigest
    let items: [FocusItem]
    let doneIDs: Set<String>
    var compact = false

    var body: some View {
        HStack(alignment: .top, spacing: Mosaic.Space.l) {
            VStack(alignment: .leading, spacing: Mosaic.Space.xs) {
                Text(Date.now, format: .dateTime.weekday(.wide).day().month(.wide))
                    .font(Mosaic.Typeface.dateEyebrow)
                    .textCase(.uppercase)
                    .kerning(1.2)
                    .foregroundStyle(Mosaic.Palette.inkTertiary)
                Text("Your ten")
                    .font(compact ? .system(size: 22, weight: .semibold, design: .serif) : Mosaic.Typeface.largeTitle)
                    .foregroundStyle(Mosaic.Palette.ink)
                if !digest.headline.isEmpty {
                    Text(digest.headline)
                        .font(Mosaic.Typeface.headline)
                        .foregroundStyle(Mosaic.Palette.inkSecondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 0)
            ProgressRosette(items: items, doneIDs: doneIDs, diameter: compact ? 56 : 72)
        }
    }
}

// MARK: - Progress rosette
// Ten star tiles around a centre medallion. Open item = outlined in its
// glaze; done = solid ("laid"). The centre shows how many are still open.

struct ProgressRosette: View {
    let items: [FocusItem]
    let doneIDs: Set<String>
    var diameter: CGFloat = 72

    var body: some View {
        let open = items.filter { !doneIDs.contains($0.id) }.count
        ZStack {
            ForEach(Array(items.prefix(10).enumerated()), id: \.element.id) { idx, item in
                let angle = Angle.degrees(Double(idx) / 10 * 360 - 90)
                let r = diameter / 2 - diameter * 0.11
                Tessera(shape: .star, color: item.tone.glaze,
                        filled: doneIDs.contains(item.id), size: diameter * 0.2)
                    .offset(x: cos(angle.radians) * r, y: sin(angle.radians) * r)
                    .animation(Mosaic.Motion.settle, value: doneIDs)
            }
            Text("\(open)")
                .font(.system(size: diameter * 0.28, weight: .regular, design: .serif))
                .foregroundStyle(Mosaic.Palette.ink)
                .contentTransition(.numericText())
        }
        .frame(width: diameter, height: diameter)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(open) of \(items.count) still open")
    }
}

// MARK: - Chips

struct MetaChip: View {
    var text: String
    var systemImage: String? = nil
    var tint: Color = Mosaic.Palette.inkSecondary
    var tessera: Color? = nil

    var body: some View {
        HStack(spacing: 4) {
            if let tessera { Tessera(shape: .star, color: tessera, size: 8) }
            if let systemImage { Image(systemName: systemImage).imageScale(.small) }
            Text(text).lineLimit(1)
        }
        .font(Mosaic.Typeface.chip)
        .foregroundStyle(tint)
        .padding(.horizontal, 6).padding(.vertical, 2.5)
        .background(tint.opacity(0.08), in: RoundedRectangle(cornerRadius: Mosaic.Radius.chip, style: .continuous))
    }
}

struct ItemChips: View {
    let item: FocusItem

    var body: some View {
        HStack(spacing: Mosaic.Space.xs) {
            if item.source == .selfNote {
                MetaChip(text: "Note to self", tint: Mosaic.Palette.teal, tessera: Mosaic.Palette.teal)
            } else {
                MetaChip(text: item.chatName, systemImage: "bubble.left")
            }
            if let due = item.due {
                MetaChip(text: Self.dueText(due, overdue: item.isOverdue),
                         systemImage: item.isOverdue ? "exclamationmark.circle" : "clock",
                         tint: item.isOverdue ? Mosaic.Palette.terracotta : Mosaic.Palette.inkSecondary)
            }
            if item.waitingOn == .them {
                MetaChip(text: "Waiting on them", systemImage: "hourglass", tint: Mosaic.Palette.indigo)
            }
        }
    }

    static func dueText(_ d: Date, overdue: Bool) -> String {
        if overdue { return "Overdue" }
        let cal = Calendar.current
        if cal.isDateInToday(d) { return "Today" }
        if cal.isDateInTomorrow(d) { return "Tomorrow" }
        return d.formatted(.dateTime.weekday(.abbreviated))
    }
}

// MARK: - Rank numeral

struct RankNumeral: View {
    let rank: Int
    var hero = false
    var body: some View {
        Text("\(rank)")
            .font(hero ? Mosaic.Typeface.rankHero : Mosaic.Typeface.rank)
            .foregroundStyle(hero ? Mosaic.Palette.ink : Mosaic.Palette.inkTertiary)
            .monospacedDigit()
            .frame(width: hero ? 44 : 22, alignment: hero ? .leading : .trailing)
            .accessibilityHidden(true)
    }
}

// MARK: - Hover actions

struct RowActions: View {
    let item: FocusItem
    let isDone: Bool
    let onToggleDone: () -> Void

    var body: some View {
        HStack(spacing: 2) {
            if let jid = item.chatJID, let url = WhatsAppLink.url(for: jid) {
                IconButton(systemImage: "arrow.up.forward.app", help: "Open in WhatsApp") {
                    NSWorkspace.shared.open(url)
                }
            }
            IconButton(systemImage: isDone ? "arrow.uturn.backward.circle" : "checkmark.circle",
                       help: isDone ? "Mark as open" : "Mark done", action: onToggleDone)
        }
    }
}

struct IconButton: View {
    let systemImage: String
    let help: String
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 13, weight: .regular))
                .frame(width: 24, height: 24)
                .foregroundStyle(hover ? Mosaic.Palette.ink : Mosaic.Palette.inkSecondary)
                .background(hover ? Mosaic.Palette.grout : .clear, in: Circle())
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
        .help(help)
        .accessibilityLabel(help)
    }
}

enum WhatsAppLink {
    /// 1:1 chats deep-link by phone; groups have no public deep link → nil.
    static func url(for jid: String) -> URL? {
        guard jid.hasSuffix("@s.whatsapp.net"),
              let phone = jid.split(separator: "@").first else { return nil }
        return URL(string: "whatsapp://send?phone=\(phone)")
    }
}

// MARK: - Card surface

struct MosaicCard: ViewModifier {
    var radius: CGFloat = Mosaic.Radius.card
    func body(content: Content) -> some View {
        content
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .background(Mosaic.Palette.card, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous)
                .strokeBorder(Mosaic.Palette.cardStroke, lineWidth: 0.5))
            .shadow(color: .black.opacity(0.05), radius: 12, y: 4)
    }
}

extension View {
    func mosaicCard(radius: CGFloat = Mosaic.Radius.card) -> some View { modifier(MosaicCard(radius: radius)) }
}
