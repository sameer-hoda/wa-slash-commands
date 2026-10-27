import AppKit
import SwiftUI

// MosaicApp — Mac menu-bar + setup-window shell.
// The main window is a plain AppKit NSWindow hosting SwiftUI: deterministic,
// always retained, ordered front on launch. (A WindowGroup scene never
// instantiated its window in this codebase, so it was removed.)

// Retained for the app's lifetime; a released NSWindow vanishes with it.
private var setupWindow: NSWindow?

@main
struct MosaicApp: App {
    @StateObject private var supervisor: Supervisor
    @StateObject private var setup: SetupModel
    @AppStorage("onboarded") private var onboarded = false

    init() {
        let sup = Supervisor()
        let mod = SetupModel()
        mod.onKeyValidated = { [weak sup] key in sup?.saveGeminiKey(key) }
        _supervisor = StateObject(wrappedValue: sup)
        _setup = StateObject(wrappedValue: mod)
        // Snapshot mode must NEVER start a supervisor: a competing bridge
        // would fight the user's live WhatsApp session for the same ports
        // and pairing. It only renders, then exits.
        if CommandLine.arguments.contains("--render-shot") {
            DispatchQueue.main.async { renderShotAndExit() }
            return
        }
        DispatchQueue.main.async {
            sup.start(); mod.start()
            showSetupWindow(supervisor: sup, setup: mod)
            NSApplication.shared.activate(ignoringOtherApps: true)
        }
        // Re-assert the window front and center shortly after launch —
        // a utility app must never leave its only window behind.
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            setupWindow?.makeKeyAndOrderFront(nil)
            NSApplication.shared.activate(ignoringOtherApps: true)
        }
    }

    var body: some Scene {
        MenuBarExtra("Mosaic", systemImage: supervisor.menuIcon) {
            MenuPopover(supervisor: supervisor, setup: setup)
                .task { supervisor.start() }
        }
        Settings {
            SettingsView(supervisor: supervisor)
        }
    }
}

private func showSetupWindow(supervisor: Supervisor, setup: SetupModel) {
    if setupWindow == nil {
        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 600),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered, defer: false)
        win.title = "Welcome to Mosaic"
        win.center()
        win.contentView = NSHostingView(rootView:
            OnboardingView(supervisor: supervisor, setup: setup))
        setupWindow = win
    }
    setupWindow?.makeKeyAndOrderFront(nil)
}

/// Hidden diagnostic: render the setup window offscreen to a file and
/// exit. Lets automated checks see the real UI without screen capture.
/// Self-gated on --render-shot so App.init captures nothing.
func renderShotAndExit() {
    guard CommandLine.arguments.contains("--render-shot") else { return }
    DispatchQueue.main.async { renderShotAndExitMain() }
}

@MainActor
private func renderShotAndExitMain() {
    let args = CommandLine.arguments
    let outPath: String = {
        if let i = args.firstIndex(of: "--render-shot"), i + 1 < args.count {
            return args[i + 1]
        }
        return "/tmp/mosaic-shot.png"
    }()
    // Offscreen ImageRenderer mangles standard controls in headless
    // sessions (proven: even bare Text renders as color bars), so the PNG
    // is only a smoke artifact. The real assertion is the state line on
    // stderr: it proves the app reached the right stage against a live
    // bridge. True pixels are verified on a real display.
    let supervisor = Supervisor()
    let setup = SetupModel()
    setup.start()
    DispatchQueue.main.asyncAfter(deadline: .now() + 6.0) {
        let s = setup.state
        fputs("render-shot reachable=\(setup.reachable) gemini_key=\(s.gemini_key) paired=\(s.paired) mechat=\(s.mechat_jid.isEmpty ? "-" : s.mechat_jid) qr=\(s.qr_data_url.isEmpty ? "-" : "present")\n", stderr)
        let view = OnboardingView(supervisor: supervisor, setup: setup)
            .frame(width: 560)
        if let img = ImageRenderer(content: view).nsImage,
           let tiff = img.tiffRepresentation,
           let rep = NSBitmapImageRep(data: tiff),
           let png = rep.representation(using: .png, properties: [:]) {
            try? png.write(to: URL(fileURLWithPath: outPath))
        }
        exit(0)
    }
}
