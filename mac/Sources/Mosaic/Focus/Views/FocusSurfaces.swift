import SwiftUI
import AppKit

// MARK: - Menu-bar popover (MenuBarExtra, .menuBarExtraStyle(.window))
//
//  ┌──────────── 380 ────────────┐
//  │ ✦✦✦ zellige band (fades) ✦✦✦│
//  │ TUESDAY 27 OCTOBER     (✦7✦)│
//  │ Your ten                    │
//  │ Launch is gated on…         │
//  ├─────────────────────────────┤
//  │ 1 ✦ Send Acme the Q4 deck   │
//  │ 2 ✦ Lock starter pricing    │
//  │ …                 (scrolls) │
//  ├─────────────────────────────┤
//  │ Updated 12 min ago  ↻  ⧉    │
//  └─────────────────────────────┘

struct FocusPopover: View {
    @ObservedObject var store: FocusStore
    var openWindow: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            FocusHeader(digest: store.digest, items: store.visibleItems,
                        doneIDs: store.doneIDs, compact: true)
                .padding(.horizontal, Mosaic.Space.l)
                .padding(.top, Mosaic.Space.xl)
                .padding(.bottom, Mosaic.Space.m)

            Divider().overlay(Mosaic.Palette.grout)

            FocusList(store: store)
                .frame(maxHeight: Mosaic.Size.popoverMaxHeight - 200)

            if store.digest.items.isEmpty && store.syncing {
                SyncBar(chats: store.syncedChats)
                    .padding(.horizontal, Mosaic.Space.m)
                    .padding(.vertical, Mosaic.Space.s)
            }

            Divider().overlay(Mosaic.Palette.grout)

            RefreshFooter(store: store, openWindow: openWindow)
                .padding(.horizontal, Mosaic.Space.m)
                .padding(.vertical, Mosaic.Space.s)
        }
        .frame(width: Mosaic.Size.popoverWidth)
        .background(ZelligeBackground(fade: .topBand(height: 120), cell: 36))
        .task { store.start() }
    }
}

struct FocusList: View {
    @ObservedObject var store: FocusStore

    var body: some View {
        Group {
            if store.digest.items.isEmpty {
                if store.lastSuccess == nil { SkeletonList() } else { AllClearState() }
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(Array(store.visibleItems.enumerated()), id: \.element.id) { idx, item in
                            FocusRow(item: item, isDone: store.doneIDs.contains(item.id)) {
                                store.toggleDone(item)
                            }
                            .transition(AnyTransition.asymmetric(
                                insertion: .opacity.combined(with: .offset(y: 6))
                                    .animation(Mosaic.Motion.settle.delay(Double(idx) * Mosaic.Motion.stagger)),
                                removal: .opacity))
                        }
                    }
                    .padding(.horizontal, Mosaic.Space.xs)
                    .padding(.vertical, Mosaic.Space.xs)
                }
                .scrollIndicators(.never)
            }
        }
    }
}

// MARK: - Main window
//
//  ┌──────────────────────── 720 ────────────────────────┐
//  │ ✦ zellige ground on the edges, plaster centre ✦      │
//  │   TUESDAY 27 OCTOBER                       (✦7✦)    │
//  │   Your ten                                          │
//  │   Launch is gated on pricing copy and the Acme deck.│
//  │  ┌─────────┐ ┌─────────┐ ┌─────────┐               │
//  │  │ 1  hero │ │ 2  hero │ │ 3  hero │               │
//  │  └─────────┘ └─────────┘ └─────────┘               │
//  │  ┌──────────────────────────────────────────┐      │
//  │  │ 4 … 10 compact rows                      │      │
//  │  └──────────────────────────────────────────┘      │
//  │   Updated 12 min ago · next 9:14 PM      ↻          │
//  └─────────────────────────────────────────────────────┘

struct FocusWindowView: View {
    @ObservedObject var store: FocusStore

    var body: some View {
        let items = store.visibleItems
        let heroes = Array(items.filter { !store.doneIDs.contains($0.id) }.prefix(3))
        let rest = items.filter { item in !heroes.contains(where: { $0.id == item.id }) }
        let showSync = items.isEmpty && store.syncing

        VStack(spacing: 0) {
        ScrollView {
            VStack(alignment: .leading, spacing: Mosaic.Space.xl) {
                FocusHeader(digest: store.digest, items: items, doneIDs: store.doneIDs)

                if items.isEmpty {
                    Group {
                        if store.lastSuccess == nil { SkeletonList() } else { AllClearState() }
                    }
                    .mosaicCard()
                } else {
                    HStack(alignment: .top, spacing: Mosaic.Space.m) {
                        ForEach(heroes) { item in
                            HeroTile(item: item, isDone: false) { store.toggleDone(item) }
                        }
                    }
                    if !rest.isEmpty {
                        VStack(spacing: 0) {
                            ForEach(rest) { item in
                                FocusRow(item: item, isDone: store.doneIDs.contains(item.id)) {
                                    store.toggleDone(item)
                                }
                                if item.id != rest.last?.id {
                                    Divider().overlay(Mosaic.Palette.grout).padding(.leading, 52)
                                }
                            }
                        }
                        .padding(Mosaic.Space.xs)
                        .mosaicCard()
                    }
                }

                RefreshFooter(store: store, openWindow: nil)
            }
            .padding(.horizontal, Mosaic.Space.xxl)
            .padding(.vertical, Mosaic.Space.xxl)
            .frame(maxWidth: 820)
            .frame(maxWidth: .infinity)
        }
        .scrollIndicators(.automatic)
        if showSync {
            Divider().overlay(Mosaic.Palette.grout)
            SyncBar(chats: store.syncedChats)
                .padding(.horizontal, Mosaic.Space.xxl)
                .padding(.vertical, Mosaic.Space.m)
        }
        }
        .frame(minWidth: Mosaic.Size.windowMin.width, minHeight: Mosaic.Size.windowMin.height)
        .background(ZelligeBackground(fade: .vignette))
        .toolbarBackground(.hidden, for: .windowToolbar)
        .task { store.start() }
        .animation(Mosaic.Motion.reorder, value: store.doneIDs)
    }
}

// MARK: - Footer

struct RefreshFooter: View {
    @ObservedObject var store: FocusStore
    var openWindow: (() -> Void)?

    var body: some View {
        HStack(spacing: Mosaic.Space.s) {
            StatusDot(phase: store.phase)
            TimelineView(.periodic(from: .now, by: 30)) { _ in
                Text(statusText)
                    .font(Mosaic.Typeface.footer)
                    .foregroundStyle(Mosaic.Palette.inkTertiary)
            }
            Spacer()
            IconButton(systemImage: "arrow.clockwise", help: "Refresh now (⌘R)") {
                Task { await store.refresh(force: true) }
            }
            .rotationEffect(.degrees(store.phase == .refreshing ? 360 : 0))
            .animation(store.phase == .refreshing
                       ? .linear(duration: 1).repeatForever(autoreverses: false) : .default,
                       value: store.phase == .refreshing)
            .keyboardShortcut("r", modifiers: .command)
            .disabled(store.phase == .refreshing)
            if let openWindow {
                IconButton(systemImage: "macwindow", help: "Open Mosaic", action: openWindow)
            }
        }
    }

    private var statusText: String {
        // While history is still arriving with nothing ranked, say so —
        // never show an error for a sync in progress.
        if store.digest.items.isEmpty && store.syncing { return "Syncing chats…" }
        // Ranker-typed failures explain themselves; only fall back to the
        // generic message when nothing ranked and no reason is known.
        if store.digest.items.isEmpty, let reason = store.failureReason {
            switch reason {
            case "no-chats": return "No recent chats to rank yet"
            case "gemini": return "Gemini call failed — check the key in Settings"
            default: break
            }
        }
        switch store.phase {
        case .refreshing: return "Re-ranking your chats…"
        case .failed(let msg):
            if let t = store.lastSuccess { return "\(msg) · showing \(t.formatted(.relative(presentation: .named)))" }
            return msg
        case .idle:
            guard let t = store.lastSuccess else { return "Waiting for first ranking…" }
            let next = store.nextRefresh.map { " · next \($0.formatted(date: .omitted, time: .shortened))" } ?? ""
            return "Updated \(t.formatted(.relative(presentation: .named)))\(next)"
        }
    }
}

struct StatusDot: View {
    let phase: FocusStore.Phase
    var body: some View {
        Tessera(shape: .diamond, color: color, size: 8)
    }
    private var color: Color {
        switch phase {
        case .idle: Mosaic.Palette.teal
        case .refreshing: Mosaic.Palette.ochre
        case .failed: Mosaic.Palette.terracotta
        }
    }
}

// MARK: - First-scan sync bar
//
// Thin 2 pt indeterminate bar with one quiet line. Shows ONLY while history
// is still arriving and nothing is ranked yet — so a fresh pairing reads as
// "syncing", never as a broken Top 10.

struct SyncBar: View {
    var chats: Int
    @State private var slide = false

    var body: some View {
        VStack(spacing: 6) {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Mosaic.Palette.grout)
                    Capsule()
                        .fill(Mosaic.Palette.teal)
                        .frame(width: max(48, geo.size.width * 0.25))
                        .offset(x: slide ? max(0, geo.size.width - max(48, geo.size.width * 0.25)) : 0)
                }
            }
            .frame(height: 2)
            .accessibilityHidden(true)
            Text(chats > 0 ? "Syncing chats… \(chats) so far" : "Syncing chats…")
                .font(Mosaic.Typeface.footer)
                .foregroundStyle(Mosaic.Palette.inkTertiary)
        }
        .onAppear {
            guard !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion else { return }
            withAnimation(.linear(duration: 1.4).repeatForever(autoreverses: true)) { slide = true }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(chats > 0 ? "Syncing chats, \(chats) so far" : "Syncing chats")
    }
}

// MARK: - Empty & loading states

/// First launch: grout-only outlines of 5 rows, breathing gently.
struct SkeletonList: View {
    @State private var on = false
    var body: some View {
        VStack(alignment: .leading, spacing: Mosaic.Space.l) {
            ForEach(0..<5, id: \.self) { i in
                HStack(spacing: Mosaic.Space.s) {
                    Tessera(shape: .star, color: Mosaic.Palette.inkTertiary, filled: false)
                    RoundedRectangle(cornerRadius: 4).fill(Mosaic.Palette.grout)
                        .frame(width: CGFloat([220, 180, 240, 160, 200][i]), height: 10)
                }
            }
            Text("Reading your work chats…")
                .font(Mosaic.Typeface.why)
                .foregroundStyle(Mosaic.Palette.inkTertiary)
        }
        .padding(Mosaic.Space.l)
        .frame(maxWidth: .infinity, alignment: .leading)
        .opacity(on ? 1 : 0.5)
        .onAppear {
            guard !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion else { return }
            withAnimation(.easeInOut(duration: 1.2).repeatForever()) { on = true }
        }
        .accessibilityLabel("Loading your top ten")
    }
}

/// Nothing pressing: one glazed medallion on plaster.
struct AllClearState: View {
    var body: some View {
        VStack(spacing: Mosaic.Space.m) {
            ZStack {
                Tessera(shape: .star, color: Mosaic.Palette.cream, size: 56)
                Tessera(shape: .star, color: Mosaic.Palette.teal, size: 26)
            }
            Text("Nothing pressing")
                .font(.system(size: 17, weight: .semibold, design: .serif))
                .foregroundStyle(Mosaic.Palette.ink)
            Text("Your work chats are quiet. Next check within the hour.")
                .font(Mosaic.Typeface.why)
                .foregroundStyle(Mosaic.Palette.inkSecondary)
                .multilineTextAlignment(.center)
        }
        .padding(Mosaic.Space.xxl)
        .frame(maxWidth: .infinity)
    }
}

// MARK: - Previews
// (Xcode #Preview blocks removed: the CLT swiftc used by ./build.sh cannot
// expand preview macros. Visuals are verified via --render-shot-focus.)
