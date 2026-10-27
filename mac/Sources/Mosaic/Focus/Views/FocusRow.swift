import SwiftUI

// FocusRow — one item, compact. Used for all 10 in the popover and for
// ranks 4–10 in the window.
//
//  ┌──────────────────────────────────────────────────────────────┐
//  │  4 ✦  Reply to Meera on the iOS checkout redirect      ⤴ ✓  │
//  │       Blocking QA sign-off for Thursday's launch.            │
//  │       [💬 Launch Squad] [⏱ Today]                            │
//  └──────────────────────────────────────────────────────────────┘

struct FocusRow: View {
    let item: FocusItem
    let isDone: Bool
    let onToggleDone: () -> Void

    @State private var hover = false

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: Mosaic.Space.s) {
            RankNumeral(rank: item.rank)
            Tessera(shape: .star, color: item.tone.glaze, filled: !isDone)
                .alignmentGuide(.firstTextBaseline) { $0[VerticalAlignment.center] + 4 }

            VStack(alignment: .leading, spacing: 3) {
                Text(item.title)
                    .font(Mosaic.Typeface.rowTitle)
                    .foregroundStyle(isDone ? Mosaic.Palette.inkTertiary : Mosaic.Palette.ink)
                    .strikethrough(isDone, color: Mosaic.Palette.inkTertiary)
                    .lineLimit(2)
                if !isDone {
                    Text(item.why)
                        .font(Mosaic.Typeface.why)
                        .foregroundStyle(Mosaic.Palette.inkSecondary)
                        .lineLimit(hover ? 3 : 1)
                    ItemChips(item: item).padding(.top, 2)
                }
            }
            Spacer(minLength: Mosaic.Space.s)

            RowActions(item: item, isDone: isDone, onToggleDone: onToggleDone)
                .opacity(hover ? 1 : 0)
        }
        .padding(.vertical, Mosaic.Space.s + 2)
        .padding(.horizontal, Mosaic.Space.m)
        .background(hover ? Mosaic.Palette.grout.opacity(0.6) : .clear,
                    in: RoundedRectangle(cornerRadius: Mosaic.Radius.row, style: .continuous))
        .contentShape(Rectangle())
        .onHover { h in withAnimationIfAllowed(Mosaic.Motion.hover) { hover = h } }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(a11yLabel)
        .accessibilityAction(named: Text(actionName), onToggleDone)
    }

    private var actionName: String { isDone ? "Mark as open" : "Mark done" }

    private var a11yLabel: String {
        var parts = ["Number \(item.rank).", item.title + ".", item.why]
        if item.source == .selfNote { parts.append("Note to self.") } else { parts.append("From \(item.chatName).") }
        if item.isOverdue { parts.append("Overdue.") }
        if isDone { parts.append("Done.") }
        return parts.joined(separator: " ")
    }
}

// HeroTile — ranks 1–3 in the window. A glazed strip of tesserae on the
// leading edge carries the tone; the numeral is big serif, like a
// museum label.

struct HeroTile: View {
    let item: FocusItem
    let isDone: Bool
    let onToggleDone: () -> Void
    @State private var hover = false

    var body: some View {
        VStack(alignment: .leading, spacing: Mosaic.Space.s) {
            HStack(alignment: .firstTextBaseline) {
                RankNumeral(rank: item.rank, hero: true)
                Spacer()
                RowActions(item: item, isDone: isDone, onToggleDone: onToggleDone)
                    .opacity(hover ? 1 : 0.0)
            }
            Text(item.title)
                .font(Mosaic.Typeface.heroTitle)
                .foregroundStyle(isDone ? Mosaic.Palette.inkTertiary : Mosaic.Palette.ink)
                .strikethrough(isDone, color: Mosaic.Palette.inkTertiary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            Text(item.why)
                .font(Mosaic.Typeface.why)
                .foregroundStyle(Mosaic.Palette.inkSecondary)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            ItemChips(item: item)
        }
        .padding(Mosaic.Space.l)
        .padding(.leading, Mosaic.Space.s)
        .frame(maxWidth: .infinity, minHeight: 168, alignment: .topLeading)
        .overlay(alignment: .leading) { GlazeStrip(color: item.tone.glaze).opacity(isDone ? 0.3 : 1) }
        .mosaicCard()
        .scaleEffect(hover ? 1.012 : 1)
        .onHover { h in withAnimationIfAllowed(Mosaic.Motion.hover) { hover = h } }
        .accessibilityElement(children: .combine)
        .accessibilityAction(named: Text(actionName), onToggleDone)
    }

    private var actionName: String { isDone ? "Mark as open" : "Mark done" }
}

/// A vertical run of small star tiles — the hero card's tone marker.
struct GlazeStrip: View {
    let color: Color
    var body: some View {
        VStack(spacing: 3) {
            ForEach(0..<6, id: \.self) { i in
                Tessera(shape: i.isMultiple(of: 2) ? .star : .diamond,
                        color: color.opacity(i.isMultiple(of: 2) ? 0.9 : 0.45), size: 7)
            }
        }
        .padding(.leading, 9)
    }
}
