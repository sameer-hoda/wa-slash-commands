import SwiftUI

// Native setup flow — renders live bridge state, no browser needed.
// Stage order: key → pair → me chat → done. The window always shows the
// first incomplete stage; completed stages collapse to a status line.

struct OnboardingView: View {
    @ObservedObject var supervisor: Supervisor
    @ObservedObject var setup: SetupModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HeaderView()
            if !setup.reachable {
                StatusLine(text: "Starting local bridge…", tone: .waiting)
            } else if setup.state.gemini_key != "valid" {
                KeyStage(setup: setup)
            } else if !setup.state.paired {
                PairStage(setup: setup)
            } else if setup.state.mechat_jid.isEmpty {
                MeChatStage(setup: setup)
            } else {
                DoneStage(setup: setup)
            }
        }
        .padding(24)
        .frame(width: 560)
        .task { setup.start() }
    }
}

private enum Tone { case waiting, ok, bad }

private struct StatusLine: View {
    var text: String
    var tone: Tone = .waiting
    var body: some View {
        HStack(spacing: 7) {
            Circle().frame(width: 7, height: 7)
                .foregroundStyle(tone == .ok ? .green : tone == .bad ? .red : .yellow)
            Text(text).font(.callout).foregroundStyle(.secondary)
        }
        .padding(.vertical, 5).padding(.horizontal, 11)
        .background(tone == .ok ? Color.green.opacity(0.07) : Color.yellow.opacity(0.07))
        .clipShape(Capsule())
    }
}

private struct HeaderView: View {
    var body: some View {
        HStack(spacing: 13) {
            Image(nsImage: NSApp.applicationIconImage)
                .resizable().frame(width: 40, height: 40)
            VStack(alignment: .leading, spacing: 2) {
                Text("Mosaic").font(.title3).fontWeight(.semibold)
                Text("Slash commands, answered in your Me chat.")
                    .font(.callout).foregroundStyle(.secondary)
            }
        }
    }
}

private struct KeyStage: View {
    @ObservedObject var setup: SetupModel
    @State private var key = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Gemini API key").font(.headline)
            HStack(spacing: 10) {
                SecureField("Paste key from Google AI Studio", text: $key)
                    .textFieldStyle(.roundedBorder)
                Button("Save & test") { setup.saveKey(key); key = "" }
                    .keyboardShortcut(.defaultAction)
            }
            if let msg = setup.keyMessage {
                Text(msg).font(.callout)
                    .foregroundStyle(setup.keyOk ? .green : .red)
            } else {
                Text("Stored only on this Mac, never sent anywhere except Google Gemini.")
                    .font(.callout).foregroundStyle(.secondary)
            }
        }
    }
}

private struct PairStage: View {
    @ObservedObject var setup: SetupModel
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if setup.state.gemini_key == "valid" {
                StatusLine(text: "Key works — answers are on.", tone: .ok)
            }
            StatusLine(text: "Waiting for pairing")
            if let img = setup.qrImage() {
                Image(nsImage: img)
                    .resizable().interpolation(.none)
                    .frame(width: 232, height: 232)
                    .background(.white).cornerRadius(12)
                    .frame(maxWidth: .infinity)
            } else {
                Text("Preparing a fresh code…")
                    .font(.callout).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity).padding(.vertical, 40)
            }
            VStack(alignment: .leading, spacing: 7) {
                Label("Open WhatsApp on your phone", systemImage: "1.circle")
                Label("Settings → Linked devices → Link a device", systemImage: "2.circle")
                Label("Point your camera at this screen", systemImage: "3.circle")
            }
            .font(.callout).foregroundStyle(.secondary)
            .labelStyle(.titleAndIcon)
        }
    }
}

private struct MeChatStage: View {
    @ObservedObject var setup: SetupModel
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            StatusLine(text: setup.state.connected ? "Connected — finding your Me chat…" : "Reconnecting…")
            Text("Send yourself any message on WhatsApp first — open your own chat, say hello, and this page fills in on its own.")
                .font(.callout).foregroundStyle(.secondary)
        }
    }
}

private struct DoneStage: View {
    @ObservedObject var setup: SetupModel
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            StatusLine(text: "Connected as +\(setup.state.mechat_phone)", tone: .ok)
            Text("Type /help in any chat — the answer lands in your Me chat.")
                .font(.callout).foregroundStyle(.secondary)
        }
    }
}

struct MenuPopover: View {
    @ObservedObject var supervisor: Supervisor
    @ObservedObject var setup: SetupModel

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(supervisor.status).font(.headline)
            Text(summary).font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("Open Setup") { NSApplication.shared.activate(ignoringOtherApps: true) }
                Button("Quit") { NSApplication.shared.terminate(nil) }
            }
        }
        .padding(12).frame(width: 280)
        .task { supervisor.start(); setup.start() }
    }

    private var summary: String {
        if !setup.reachable { return "Bridge starting…" }
        if setup.state.gemini_key != "valid" { return "Gemini key needed" }
        if !setup.state.paired { return "Waiting for QR scan" }
        if setup.state.mechat_jid.isEmpty { return "Finding Me chat…" }
        return "Connected as +\(setup.state.mechat_phone)"
    }
}

struct SettingsView: View {
    @ObservedObject var supervisor: Supervisor
    var body: some View {
        TabView {
            Text("General").tabItem { Text("General") }
            Text("Gemini").tabItem { Text("Gemini") }
            Text("WhatsApp").tabItem { Text("WhatsApp") }
            Text("Privacy").tabItem { Text("Privacy") }
            Text("Advanced").tabItem { Text("Advanced") }
        }.frame(width: 480, height: 320)
    }
}
