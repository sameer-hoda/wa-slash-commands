import AppKit
import SwiftUI

// Window + menu-bar helpers for the Focus surfaces.
// Mirrors the retained-NSWindow pattern MosaicApp already uses for setup
// (a WindowGroup never instantiated its window in this codebase).

@MainActor
enum FocusWindow {
    private static var window: NSWindow?

    static func show(store: FocusStore) {
        if window == nil {
            let win = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 760, height: 780),
                styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                backing: .buffered, defer: false)
            win.title = "Mosaic"
            win.titlebarAppearsTransparent = true
            win.titleVisibility = .hidden
            win.isMovableByWindowBackground = true
            win.isReleasedWhenClosed = false
            win.minSize = Mosaic.Size.windowMin
            win.setFrameAutosaveName("MosaicFocusWindow")
            win.contentView = NSHostingView(rootView: FocusWindowView(store: store))
            win.center()
            window = win
        }
        window?.makeKeyAndOrderFront(nil)
        NSApplication.shared.activate(ignoringOtherApps: true)
    }
}

/// 8-point star as a template image for the menu bar (tints with the system).
enum MenuBarStar {
    static let image: NSImage = {
        let size = NSSize(width: 16, height: 16)
        let img = NSImage(size: size, flipped: false) { rect in
            let c = CGPoint(x: rect.midX, y: rect.midY)
            let path = ZelligeBackground.starPath(center: c, R: 7.5, points: 8, innerRatio: 0.7654)
            let ns = NSBezierPath()
            path.forEach { el in
                switch el {
                case .move(to: let p): ns.move(to: p)
                case .line(to: let p): ns.line(to: p)
                case .closeSubpath: ns.close()
                default: break
                }
            }
            NSColor.black.setFill()
            ns.fill()
            // Small hollow centre so it reads as a tile, not a blob.
            NSColor.clear.set()
            let hole = NSBezierPath(ovalIn: NSRect(x: c.x - 1.6, y: c.y - 1.6, width: 3.2, height: 3.2))
            NSGraphicsContext.current?.compositingOperation = .clear
            hole.fill()
            return true
        }
        img.isTemplate = true
        img.accessibilityDescription = "Mosaic"
        return img
    }()
}
