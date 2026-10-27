import AppKit
import Combine
import Foundation
import SwiftUI

// FocusStore — owns the Top 10, refreshes it every hour, survives sleep.
//
// Refresh triggers (all funnel into `refresh(force:)`):
//   • launch                • every 60 min after the last SUCCESS
//   • Mac wakes from sleep  • ⌘R / the footer button (force = true)
// Stale data always stays on screen while a refresh runs; a failure keeps
// the last good digest and only changes the footer line.

protocol FocusProvider {
    /// `force` asks the back end to re-rank now instead of serving its cache.
    func fetch(force: Bool) async throws -> FocusDigest
}

@MainActor
final class FocusStore: ObservableObject {
    enum Phase: Equatable { case idle, refreshing, failed(String) }

    @Published private(set) var digest: FocusDigest = .empty
    @Published private(set) var phase: Phase = .idle
    @Published private(set) var lastSuccess: Date?
    @Published private(set) var doneIDs: Set<String> = []
    /// First-scan history sync (fresh pairing). While true with no digest,
    /// surfaces show the thin "syncing chats" bar instead of an error.
    @Published private(set) var syncing = false
    @Published private(set) var syncedChats = 0
    /// Typed rank-failure reason from the bridge (no-chats, gemini, …).
    @Published private(set) var failureReason: String?

    /// Settings → General → Refresh interval (minutes). Default 60.
    static var interval: TimeInterval {
        let m = UserDefaults.standard.integer(forKey: "focus.intervalMinutes")
        return TimeInterval((m > 0 ? m : 60) * 60)
    }

    private let provider: FocusProvider
    private var timer: Timer?
    private var wakeObserver: NSObjectProtocol?
    private var syncTimer: Timer?
    private var wasSyncing = false
    private let doneKey = "focus.doneIDs"

    init(provider: FocusProvider) {
        self.provider = provider
        doneIDs = Set(UserDefaults.standard.stringArray(forKey: doneKey) ?? [])
    }

    /// Items to show: ranked, done ones moved to the end (kept for undo).
    var visibleItems: [FocusItem] {
        let sorted = digest.items.sorted { $0.rank < $1.rank }
        return sorted.filter { !doneIDs.contains($0.id) } + sorted.filter { doneIDs.contains($0.id) }
    }
    var openCount: Int { digest.items.filter { !doneIDs.contains($0.id) }.count }

    var nextRefresh: Date? { lastSuccess?.addingTimeInterval(Self.interval) }

    func start() {
        guard timer == nil else { return }
        startSyncWatch()
        Task { await refresh(force: false) }
        // Tick every minute; refresh when due. A minute tick (not a 1-hour
        // timer) is what makes the schedule correct after sleep/clock changes.
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in await self?.refreshIfDue() }
        }
        timer?.tolerance = 10
        wakeObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didWakeNotification, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in await self?.refreshIfDue() }
        }
    }

    func stop() {
        timer?.invalidate(); timer = nil
        if let o = wakeObserver { NSWorkspace.shared.notificationCenter.removeObserver(o) }
        wakeObserver = nil
        stopSyncWatch()
    }

    /// Short-poll /setup/state for history-sync progress, but ONLY while no
    /// digest has ever loaded. Stops itself on first success. When a running
    /// sync ends with still nothing ranked, it fires one forced refresh —
    /// the moment the most recent chat lands, the Top 10 follows.
    func startSyncWatch() {
        guard syncTimer == nil else { return }
        Task { await self.pollSync() }
        syncTimer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in await self?.pollSync() }
        }
        syncTimer?.tolerance = 5
    }

    func stopSyncWatch() {
        syncTimer?.invalidate(); syncTimer = nil
    }

    func pollSync() async {
        guard digest.items.isEmpty && lastSuccess == nil else {
            syncing = false
            stopSyncWatch()
            return
        }
        let base = (provider as? BridgeFocusProvider)?.base
            ?? ProcessInfo.processInfo.environment["MOSAIC_SETUP_URL"] ?? "http://127.0.0.1:8081"
        guard let url = URL(string: "\(base)/setup/state") else { return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 8
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let s = try JSONDecoder().decode(SetupState.self, from: data)
            let was = wasSyncing
            syncing = s.syncing_chats
            syncedChats = s.synced_chats
            wasSyncing = s.syncing_chats
            if was && !s.syncing_chats {
                await refresh(force: true)
            }
        } catch {
            syncing = false
        }
    }

    func refreshIfDue() async {
        guard let next = nextRefresh else { return await refresh(force: false) }
        if Date() >= next { await refresh(force: false) }
    }

    func refresh(force: Bool) async {
        guard phase != .refreshing else { return }
        phase = .refreshing
        do {
            let fresh = try await provider.fetch(force: force)
            withAnimationIfAllowed(Mosaic.Motion.reorder) {
                digest = fresh
            }
            lastSuccess = Date()
            // Forget "done" marks for items the model no longer returns.
            doneIDs.formIntersection(fresh.items.map(\.id))
            persistDone()
            syncing = false
            stopSyncWatch()
            failureReason = nil
            phase = .idle
        } catch {
            if let fe = error as? FocusFetchError {
                failureReason = fe.reason
                phase = .failed(fe.message)
            } else {
                phase = .failed(Self.humanize(error))
            }
        }
    }

    func toggleDone(_ item: FocusItem) {
        let nowDone = !doneIDs.contains(item.id)
        withAnimationIfAllowed(Mosaic.Motion.reorder) {
            if nowDone { doneIDs.insert(item.id) } else { doneIDs.remove(item.id) }
        }
        persistDone()
        // Feed the back-end done-memory (done.json) so the next ranking
        // never regenerates this task unless its chat has new developments.
        // Best-effort: UserDefaults above is the source of truth.
        if nowDone { syncDone(item) } else { syncUndone(item) }
    }

    private func syncDone(_ item: FocusItem) {
        postDone(id: item.id, title: item.title, chatJID: item.chatJID,
                 lastActivity: item.lastActivity, done: true)
    }

    private func syncUndone(_ item: FocusItem) {
        // Undo = forget the done-mark; the next refresh may return the item.
        postDone(id: item.id, title: "", chatJID: nil, lastActivity: nil, done: false)
    }

    private func postDone(id: String, title: String, chatJID: String?,
                          lastActivity: Date?, done: Bool) {
        let base = ProcessInfo.processInfo.environment["MOSAIC_SETUP_URL"] ?? "http://127.0.0.1:8081"
        guard let url = URL(string: "\(base)/focus/done") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 10
        let iso = lastActivity.map { ISO8601DateFormatter().string(from: $0) } ?? ""
        let body: [String: String] = done
            ? ["id": id, "title": title, "chat_jid": chatJID ?? "",
               "last_activity": iso]
            : ["id": "forget:\(id)"]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        URLSession.shared.dataTask(with: req) { _, _, _ in }.resume()
    }

    private func persistDone() {
        UserDefaults.standard.set(Array(doneIDs), forKey: doneKey)
    }

    private static func humanize(_ error: Error) -> String {
        if (error as? URLError)?.code == .cannotConnectToHost { return "Bridge offline" }
        if (error as? URLError)?.code == .timedOut { return "Gemini is slow — will retry" }
        return "Couldn’t refresh"
    }
}

// MARK: - Providers

/// Typed fetch failure: the bridge 404 carries the ranker's reason so the
/// footer can say "no chats yet" instead of a generic failure.
struct FocusFetchError: Error {
    var reason: String
    var message: String
}

/// Production: the local bridge serves the cached digest; `?refresh=1` re-ranks.
struct BridgeFocusProvider: FocusProvider {
    var base = ProcessInfo.processInfo.environment["MOSAIC_SETUP_URL"] ?? "http://127.0.0.1:8081"

    func fetch(force: Bool) async throws -> FocusDigest {
        var comps = URLComponents(string: "\(base)/focus/top10")!
        if force { comps.queryItems = [URLQueryItem(name: "refresh", value: "1")] }
        var req = URLRequest(url: comps.url!)
        req.timeoutInterval = force ? 90 : 10   // a forced Gemini run can take a while
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                throw FocusFetchError(reason: (json["reason"] as? String) ?? "unknown",
                                      message: (json["error"] as? String) ?? "Couldn't refresh")
            }
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder.focus.decode(FocusDigest.self, from: data)
    }
}

/// Fallback / dev: read `focus.json` the worker drops in Application Support.
struct FileFocusProvider: FocusProvider {
    var url: URL
    func fetch(force: Bool) async throws -> FocusDigest {
        try JSONDecoder.focus.decode(FocusDigest.self, from: Data(contentsOf: url))
    }
}

/// Previews + snapshot mode.
struct SampleFocusProvider: FocusProvider {
    func fetch(force: Bool) async throws -> FocusDigest { .sample }
}

// MARK: - Motion helper (respects Reduce Motion)

func withAnimationIfAllowed<R>(_ animation: Animation, _ body: () throws -> R) rethrows -> R {
    if NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
        return try body()
    }
    return try withAnimation(animation, body)
}
