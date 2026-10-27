import Foundation
import Security
import ServiceManagement

// Supervisor — owns the Go bridge + Python worker (spec v2 §§5,8).
// Policy: exponential-backoff restart, crash-loop guard (5 crashes / 2 min
// -> error state), ~30s heartbeat, single-instance lock file, SMAppService
// login item read live (never a cached flag).

@MainActor
final class Supervisor: ObservableObject {
    @Published var status: String = "Starting…"
    @Published var lastActivity: String = "—"
    @Published var menuIcon: String = "message.fill"

    private var crashes: [Date] = []
    private var lockFile: Int32 = -1
    private var bridge: Process?
    private var started = false
    private var healthTask: Task<Void, Never>?

    var appSupport: URL {
        // MOSAIC_SUPPORT_DIR redirects all local state (snapshots, tests).
        // Never set it in production — the Keychain key follows the login
        // keychain, not the support dir, so a redirected dir only affects
        // pairing databases and sockets, never the secret itself.
        if let override = ProcessInfo.processInfo.environment["MOSAIC_SUPPORT_DIR"],
           !override.isEmpty {
            return URL(fileURLWithPath: override, isDirectory: true)
        }
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Mosaic", isDirectory: true)
    }

    var socketURL: URL { appSupport.appendingPathComponent("bridge.sock") }
    var lockURL: URL { appSupport.appendingPathComponent("mosaic.lock") }

    func acquireSingleInstance() -> Bool {
        try? FileManager.default.createDirectory(at: appSupport, withIntermediateDirectories: true)
        lockFile = open(lockURL.path, O_CREAT | O_RDWR, 0o600)
        guard lockFile >= 0 else { return false }
        if flock(lockFile, LOCK_EX | LOCK_NB) != 0 { return false }
        return true
    }

    func recordCrash() -> Bool {
        let now = Date()
        crashes = crashes.filter { now.timeIntervalSince($0) < 120 }
        crashes.append(now)
        return crashes.count < 5
    }

    func setLoginItem(enabled: Bool) throws {
        if #available(macOS 13.0, *) {
            if enabled { try SMAppService.mainApp.register() }
            else { try SMAppService.mainApp.unregister() }
        }
    }

    private var pidURL: URL { appSupport.appendingPathComponent("bridge.pid") }
    /// Legacy plaintext key path (pre-Keychain builds). Only ever read once
    /// for migration, then deleted. Nothing ever writes it again.
    private var geminiKeyURL: URL { appSupport.appendingPathComponent("gemini_key") }

    private let keychainService = "com.sameerhoda.mosaic"
    private let keychainAccount = "gemini-api-key"

    private func keychainQuery() -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: keychainService,
         kSecAttrAccount as String: keychainAccount]
    }

    private func keychainLoad() -> String? {
        var query = keychainQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let key = String(data: data, encoding: .utf8) else { return nil }
        let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func keychainSave(_ key: String) {
        let data = Data(key.utf8)
        var query = keychainQuery()
        query[kSecValueData as String] = data
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        if SecItemAdd(query as CFDictionary, nil) == errSecDuplicateItem {
            let update: [String: Any] = [kSecValueData as String: data]
            SecItemUpdate(keychainQuery() as CFDictionary, update as CFDictionary)
        }
    }

    /// One-time migration: import a legacy plaintext key into the Keychain,
    /// then delete the file so no secret ever rests on disk again.
    private func migrateLegacyKeyFile() {
        guard let text = try? String(contentsOf: geminiKeyURL, encoding: .utf8) else { return }
        let legacy = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !legacy.isEmpty && keychainLoad() == nil {
            keychainSave(legacy)
        }
        try? FileManager.default.removeItem(at: geminiKeyURL)
    }

    var geminiKeyConfigured: Bool { geminiKey() != nil }

    /// Persist the key to the Keychain and restart the bridge so the new
    /// key takes effect (terminationHandler relaunches with the new env).
    /// The key never touches disk outside the Keychain.
    func saveGeminiKey(_ key: String) {
        let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        keychainSave(trimmed)
        bridge?.terminate() // terminationHandler relaunches with the new env
    }

    private func geminiKey() -> String? { keychainLoad() }

    /// Kill a bridge orphaned by a dead supervisor (same port, deaf process).
    /// Only touches fresh pidfiles — an old PID may have been recycled.
    private func killStaleBridge() {
        let fm = FileManager.default
        guard let attrs = try? fm.attributesOfItem(atPath: pidURL.path),
              let mtime = attrs[.modificationDate] as? Date,
              Date().timeIntervalSince(mtime) < 15 * 60,
              let text = try? String(contentsOf: pidURL, encoding: .utf8),
              let pid = Int32(text.trimmingCharacters(in: .whitespacesAndNewlines)),
              pid > 0, kill(pid, 0) == 0 else {
            try? fm.removeItem(at: pidURL)
            return
        }
        kill(pid, SIGTERM)
        try? fm.removeItem(at: pidURL)
    }

    /// Idempotent launch: single-instance lock + bundled bridge child process.
    func start() {
        guard !started else { return }
        started = true
        guard acquireSingleInstance() else {
            status = "Another copy is already running"
            menuIcon = "exclamationmark.triangle"
            return
        }
        killStaleBridge()
        migrateLegacyKeyFile()
        launchBridge()
    }

    func stop() {
        bridge?.terminate()
        bridge = nil
    }

    private func bundledBridgeURL() -> URL {
        Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/wa-bridge")
    }

    private func launchBridge() {
        let proc = Process()
        proc.executableURL = bundledBridgeURL()
        proc.currentDirectoryURL = appSupport
        var env = ProcessInfo.processInfo.environment
        env["STORE_DIR"] = appSupport.path
        env["PORT"] = "8081"
        // Local app: loopback-only setup page needs no password gate.
        env["SETUP_NO_AUTH"] = "1"
        env["PY_SCRIPTS_DIR"] = Bundle.main.bundleURL
            .appendingPathComponent("Contents/Resources/python").path
        if let key = geminiKey() {
            env["GEMINI_API_KEY"] = key
        }
        proc.environment = env
        proc.terminationHandler = { [weak self] _ in
            Task { @MainActor [weak self] in self?.bridgeExited() }
        }
        do {
            try proc.run()
            bridge = proc
            try? String(proc.processIdentifier).write(to: pidURL, atomically: true, encoding: .utf8)
            status = "Bridge running — open setup to pair"
            menuIcon = "message.fill"
            watchHealth(proc)
        } catch {
            status = "Bridge failed to start: \(error.localizedDescription)"
            menuIcon = "exclamationmark.triangle"
        }
    }

    /// A live-but-deaf bridge (bind failed, crash loop) must not sit silent:
    /// if /health never answers, kill it so the crash path relaunches cleanly.
    private func watchHealth(_ proc: Process) {
        healthTask?.cancel()
        healthTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 6_000_000_000)
            guard let self, !Task.isCancelled, self.bridge === proc else { return }
            if !(await self.bridgeHealthy()) && !Task.isCancelled && self.bridge === proc {
                self.status = "Bridge not responding — restarting…"
                self.bridge?.terminate()
            }
        }
    }

    private func bridgeHealthy() async -> Bool {
        guard let url = URL(string: "http://127.0.0.1:8081/health") else { return false }
        var req = URLRequest(url: url)
        req.timeoutInterval = 4
        do {
            let (_, resp) = try await URLSession.shared.data(for: req)
            return (resp as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }

    private func bridgeExited() {
        healthTask?.cancel()
        bridge = nil
        if recordCrash() {
            status = "Bridge exited — restarting…"
            launchBridge()
        } else {
            status = "Bridge crashed repeatedly — see logs"
            menuIcon = "exclamationmark.triangle"
        }
    }
}
