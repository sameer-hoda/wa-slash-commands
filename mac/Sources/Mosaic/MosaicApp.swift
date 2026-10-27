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
    @StateObject private var focus: FocusStore
    @AppStorage("onboarded") private var onboarded = false

    init() {
        let sup = Supervisor()
        let mod = SetupModel()
        let store = FocusStore(provider: BridgeFocusProvider())
        mod.onKeyValidated = { [weak sup] key in sup?.saveGeminiKey(key) }
        mod.onOnboarded = { [weak sup, weak store] in
            UserDefaults.standard.set(true, forKey: "onboarded")
            setupWindow?.close()
            if let store {
                FocusWindow.show(store: store)
                store.start()
            }
            _ = sup
        }
        _supervisor = StateObject(wrappedValue: sup)
        _setup = StateObject(wrappedValue: mod)
        _focus = StateObject(wrappedValue: store)
        // Snapshot mode must NEVER start a supervisor: a competing bridge
        // would fight the user's live WhatsApp session for the same ports
        // and pairing. It only renders, then exits.
        if CommandLine.arguments.contains("--render-shot")
            || CommandLine.arguments.contains("--render-shot-focus") {
            DispatchQueue.main.async { renderShotAndExit() }
            return
        }
        DispatchQueue.main.async {
            sup.start(); mod.start()
            if UserDefaults.standard.bool(forKey: "onboarded") {
                FocusWindow.show(store: store); store.start()
            } else {
                showSetupWindow(supervisor: sup, setup: mod)
            }
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
        MenuBarExtra {
            if setup.state.mechat_jid.isEmpty {
                MenuPopover(supervisor: supervisor, setup: setup)
                    .task { supervisor.start() }
            } else {
                FocusPopover(store: focus, openWindow: { FocusWindow.show(store: focus) })
            }
        } label: {
            if supervisor.menuIcon == "exclamationmark.triangle" {
                Image(systemName: "exclamationmark.triangle")
            } else {
                Image(nsImage: MenuBarStar.image)
            }
        }
        .menuBarExtraStyle(.window)
        Settings {
            SettingsView(supervisor: supervisor, setup: setup)
        }
    }
}

/// Retained setup window; internal so the menu popover can reopen it.
func showSetupWindow(supervisor: Supervisor, setup: SetupModel) {
    if setupWindow == nil {
        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 600),
            styleMask: [.titled, .closable, .miniaturizable, .fullSizeContentView],
            backing: .buffered, defer: false)
        win.title = "Welcome to Mosaic"
        win.titlebarAppearsTransparent = true
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
    guard CommandLine.arguments.contains("--render-shot")
        || CommandLine.arguments.contains("--render-shot-focus") else { return }
    DispatchQueue.main.async { renderShotAndExitMain() }
}

@MainActor
private func renderShotAndExitMain() {
    let args = CommandLine.arguments
    if args.contains("--render-shot-focus") {
        let outPath: String = {
            if let i = args.firstIndex(of: "--render-shot-focus"), i + 1 < args.count {
                return args[i + 1]
            }
            return "/tmp/mosaic-focus-shot.png"
        }()
        let store = FocusStore(provider: SampleFocusProvider())
        Task {
            await store.refresh(force: false)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) {
            fputs("render-shot-focus items=\(store.digest.items.count) headline=\(store.digest.headline.isEmpty ? "-" : "present")\n", stderr)
            let view = FocusWindowView(store: store)
                .frame(width: 760, height: 780)
            if let img = ImageRenderer(content: view).nsImage,
               let tiff = img.tiffRepresentation,
               let rep = NSBitmapImageRep(data: tiff),
               let png = rep.representation(using: .png, properties: [:]) {
                try? png.write(to: URL(fileURLWithPath: outPath))
            }
            exit(0)
        }
        return
    }
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
