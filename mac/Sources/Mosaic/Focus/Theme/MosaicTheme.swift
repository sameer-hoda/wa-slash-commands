import SwiftUI
import AppKit

// MosaicTheme — design tokens for the "Quiet Zellige" theme.
// Palette is lifted from the app icon (cream marble, glazed teal,
// terracotta, umber). Every colour is light/dark adaptive.
// RULE: views never use raw hex — only these tokens.

enum Mosaic {

    // MARK: Colour

    enum Palette {
        /// Warm plaster — the window ground.
        static let plaster   = dyn(light: 0xF7F2EA, dark: 0x17110E)
        /// Slightly deeper ground used under the pattern edges.
        static let plasterDeep = dyn(light: 0xEFE6D8, dark: 0x120D0B)
        /// Card surface (sits on top of material).
        static let card      = dyn(light: 0xFFFDF9, dark: 0x221A16, lightAlpha: 0.78, darkAlpha: 0.72)
        static let cardStroke = dyn(light: 0x2E211C, dark: 0xEFE2C8, lightAlpha: 0.08, darkAlpha: 0.10)

        /// Text
        static let ink       = dyn(light: 0x2A1F1A, dark: 0xF3EADB)
        static let inkSecondary = dyn(light: 0x2A1F1A, dark: 0xF3EADB, lightAlpha: 0.62, darkAlpha: 0.62)
        static let inkTertiary  = dyn(light: 0x2A1F1A, dark: 0xF3EADB, lightAlpha: 0.40, darkAlpha: 0.40)

        /// Glazes (tile colours) — used for accents, chips, the rosette.
        static let teal       = dyn(light: 0x1F6F6B, dark: 0x4FB3AA)
        static let terracotta = dyn(light: 0xB9562F, dark: 0xE07E57)
        static let ochre      = dyn(light: 0xC48A1E, dark: 0xE2B04F)
        static let indigo     = dyn(light: 0x2F4E7A, dark: 0x7FA3D6)
        static let cream      = dyn(light: 0xE9D9BB, dark: 0x5A4A3A)
        static let umber      = dyn(light: 0x2E211C, dark: 0xD9C9AE)

        /// Grout — the hairline between tiles. Also used for dividers.
        static let grout      = dyn(light: 0x2E211C, dark: 0xEFE2C8, lightAlpha: 0.07, darkAlpha: 0.08)
    }

    // MARK: Semantic accents

    enum Tone {
        case critical, high, normal, selfNote

        var glaze: Color {
            switch self {
            case .critical: Palette.terracotta
            case .high:     Palette.ochre
            case .normal:   Palette.indigo
            case .selfNote: Palette.teal
            }
        }
    }

    // MARK: Type (SF Pro + New York for numerals — "Apple editorial")

    enum Typeface {
        static let dateEyebrow = Font.system(size: 11, weight: .semibold).width(.expanded)
        static let largeTitle  = Font.system(size: 26, weight: .semibold, design: .serif)
        static let headline    = Font.system(size: 13, weight: .regular)
        static let rankHero    = Font.system(size: 34, weight: .regular, design: .serif)
        static let rank        = Font.system(size: 17, weight: .regular, design: .serif)
        static let heroTitle   = Font.system(size: 15, weight: .semibold)
        static let rowTitle    = Font.system(size: 13, weight: .semibold)
        static let why         = Font.system(size: 12, weight: .regular)
        static let chip        = Font.system(size: 10.5, weight: .medium)
        static let footer      = Font.system(size: 11, weight: .regular).monospacedDigit()
    }

    // MARK: Spacing / shape (8-pt grid, 4-pt half steps)

    enum Space {
        static let xxs: CGFloat = 2
        static let xs: CGFloat = 4
        static let s: CGFloat = 8
        static let m: CGFloat = 12
        static let l: CGFloat = 16
        static let xl: CGFloat = 24
        static let xxl: CGFloat = 32
    }

    enum Radius {
        static let chip: CGFloat = 6
        static let row: CGFloat = 10
        static let card: CGFloat = 14
        static let window: CGFloat = 18
    }

    // MARK: Motion

    enum Motion {
        static let hover   = Animation.spring(response: 0.25, dampingFraction: 0.9)
        static let reorder = Animation.spring(response: 0.45, dampingFraction: 0.85)
        static let settle  = Animation.easeOut(duration: 0.35)
        /// Stagger per row on refresh (tiles "laid" one by one).
        static let stagger: Double = 0.035
    }

    // MARK: Layout

    enum Size {
        static let popoverWidth: CGFloat = 380
        static let popoverMaxHeight: CGFloat = 600
        static let windowMin = CGSize(width: 640, height: 600)
        static let tessera: CGFloat = 10
        static let patternCell: CGFloat = 44
    }
}

// MARK: - Helpers

private func dyn(light: UInt32, dark: UInt32,
                 lightAlpha: CGFloat = 1, darkAlpha: CGFloat = 1) -> Color {
    Color(nsColor: NSColor(name: nil) { appearance in
        let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        return NSColor(hex: isDark ? dark : light, alpha: isDark ? darkAlpha : lightAlpha)
    })
}

extension NSColor {
    convenience init(hex: UInt32, alpha: CGFloat = 1) {
        self.init(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255,
                  green:   CGFloat((hex >> 8) & 0xFF) / 255,
                  blue:    CGFloat(hex & 0xFF) / 255,
                  alpha:   alpha)
    }
}
