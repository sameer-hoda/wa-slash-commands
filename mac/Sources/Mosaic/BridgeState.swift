import AppKit
import Foundation

// BridgeState — live setup state polled from the bundled bridge.
// The whole native window renders from this; no browser needed.

struct SetupState: Decodable {
    var paired = false
    var connected = false
    var mechat_jid = ""
    var mechat_phone = ""
    var mechat_how = ""
    var welcomed = false
    var gemini_key = ""
    var qr_data_url = ""
    var last_message_at = ""

    enum CodingKeys: String, CodingKey {
        case paired, connected, mechat_jid, mechat_phone, mechat_how,
             welcomed, gemini_key, qr_data_url, last_message_at
    }
}

@MainActor
final class SetupModel: ObservableObject {
    @Published var state = SetupState()
    @Published var reachable = false
    @Published var keyMessage: String? = nil
    @Published var keyOk = false

    private var timer: Timer?
    /// Called with the validated key so the shell can persist it (Keychain).
    var onKeyValidated: ((String) -> Void)?

    /// Snapshot/test hook: MOSAIC_SETUP_URL points at an isolated bridge.
    /// Production always uses the loopback bridge on 8081.
    private var setupBase: String {
        ProcessInfo.processInfo.environment["MOSAIC_SETUP_URL"] ?? "http://127.0.0.1:8081"
    }

    func start() {
        stop()
        Task { await self.refresh() }
        timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in await self?.refresh() }
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
    }

    func refresh() async {
        guard let url = URL(string: "\(setupBase)/setup/state") else { return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 5
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let decoded = try JSONDecoder().decode(SetupState.self, from: data)
            state = decoded
            reachable = true
        } catch {
            reachable = false
        }
    }

    func qrImage() -> NSImage? {
        let prefix = "data:image/png;base64,"
        guard state.qr_data_url.hasPrefix(prefix),
              let data = Data(base64Encoded: String(state.qr_data_url.dropFirst(prefix.count))) else {
            return nil
        }
        return NSImage(data: data)
    }

    func saveKey(_ key: String) {
        let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            keyMessage = "Paste a key first."
            keyOk = false
            return
        }
        keyMessage = "Testing key…"
        keyOk = false
        guard let url = URL(string: "\(setupBase)/setup/gemini") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 25
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["key": trimmed])
        URLSession.shared.dataTask(with: req) { [weak self] data, _, _ in
            Task { @MainActor [weak self] in
                guard let self else { return }
                if let data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   json["ok"] as? Bool == true {
                    self.keyMessage = "Key works — saved on this Mac."
                    self.keyOk = true
                    self.onKeyValidated?(trimmed)
                } else if let data,
                          let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                          json["status"] as? String == "missing" {
                    self.keyMessage = "That came back empty — paste the full key."
                    self.keyOk = false
                } else {
                    self.keyMessage = "Key rejected — check it in Google AI Studio (billing enabled)."
                    self.keyOk = false
                }
                await self.refresh()
            }
        }.resume()
    }
}
