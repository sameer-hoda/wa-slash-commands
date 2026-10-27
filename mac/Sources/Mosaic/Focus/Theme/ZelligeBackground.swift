import SwiftUI

// ZelligeBackground — the "mosaic" ground for every Mosaic surface.
//
// Geometry: a square lattice of 8-point stars (khatam: two overlapping
// squares) whose axis tips touch; the gaps at lattice corners hold a
// small 4-point cross tile. Hairline "grout" strokes outline every piece.
// Each tile gets a tiny deterministic opacity jitter so the field reads
// as hand-glazed, not printed.
//
// It is DECORATION: always low-contrast, always faded where content sits,
// removed entirely under Increase Contrast, and never animated.

struct ZelligeBackground: View {
    enum Fade {
        /// Pattern strongest at the top, dissolving downward (popover header band).
        case topBand(height: CGFloat)
        /// Pattern on the window edges, calm plaster in the centre.
        case vignette
        /// Uniform — for small decorative tiles (empty states, icon wells).
        case none
    }

    var fade: Fade = .vignette
    var cell: CGFloat = Mosaic.Size.patternCell
    /// Overall strength multiplier. 1 = spec default.
    var intensity: Double = 1

    @Environment(\.colorScheme) private var scheme
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        ZStack {
            Mosaic.Palette.plaster
            if contrast != .increased {
                pattern
                    .mask(mask)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
        }
        .ignoresSafeArea()
    }

    // MARK: Pattern

    private var pattern: some View {
        let k = intensity * (scheme == .dark ? 0.8 : 1.0)
        let teal = Mosaic.Palette.teal
        let terracotta = Mosaic.Palette.terracotta
        let ochre = Mosaic.Palette.ochre
        let cream = Mosaic.Palette.cream
        let grout = Mosaic.Palette.umber

        return Canvas(rendersAsynchronously: true) { ctx, size in
            let R = cell / 2                      // star circumradius; tips touch neighbours
            let cols = Int(ceil(size.width / cell)) + 1
            let rows = Int(ceil(size.height / cell)) + 1

            for j in 0..<rows {
                for i in 0..<cols {
                    let c = CGPoint(x: CGFloat(i) * cell, y: CGFloat(j) * cell)
                    let h = hash(i, j)

                    // 1. Big star — alternates cream / teal like a checkerboard.
                    let star = Self.starPath(center: c, R: R * 0.96, points: 8, innerRatio: 0.7654)
                    let starGlaze: Color = (i + j).isMultiple(of: 2) ? cream : teal
                    let starAlpha = ((i + j).isMultiple(of: 2) ? 0.55 : 0.10) * jitter(h) * k
                    ctx.fill(star, with: .color(starGlaze.opacity(starAlpha)))
                    ctx.stroke(star, with: .color(grout.opacity(0.07 * k)), lineWidth: 0.6)

                    // 2. Inner rosette on every 3rd teal star — the "jewel".
                    if !(i + j).isMultiple(of: 2) && h % 3 == 0 {
                        let jewel = Self.starPath(center: c, R: R * 0.38, points: 8, innerRatio: 0.7654)
                        ctx.fill(jewel, with: .color(ochre.opacity(0.16 * k)))
                    }

                    // 3. Corner cross in the gap between four stars.
                    let corner = CGPoint(x: c.x + cell / 2, y: c.y + cell / 2)
                    let cross = Self.starPath(center: corner, R: R * 0.62, points: 4, innerRatio: 0.36, rotation: .pi / 4)
                    ctx.fill(cross, with: .color(terracotta.opacity(0.10 * jitter(h &+ 7) * k)))
                    ctx.stroke(cross, with: .color(grout.opacity(0.06 * k)), lineWidth: 0.5)
                }
            }
        }
    }

    @ViewBuilder private var mask: some View {
        switch fade {
        case .topBand(let height):
            VStack(spacing: 0) {
                LinearGradient(colors: [.black, .black.opacity(0.55), .clear],
                               startPoint: .top, endPoint: .bottom)
                    .frame(height: height)
                Color.clear
            }
        case .vignette:
            RadialGradient(colors: [.clear, .clear, .black.opacity(0.7), .black],
                           center: .center, startRadius: 0, endRadius: 520)
        case .none:
            Color.black
        }
    }

    // MARK: Geometry

    /// Regular star polygon. `innerRatio` 0.7654 gives the classic khatam
    /// (two overlapping squares) for points = 8.
    static func starPath(center c: CGPoint, R: CGFloat, points n: Int,
                         innerRatio: CGFloat, rotation: CGFloat = 0) -> Path {
        var p = Path()
        let r = R * innerRatio
        for k in 0..<(n * 2) {
            let a = rotation + CGFloat(k) * .pi / CGFloat(n) - .pi / 2
            let rad = k.isMultiple(of: 2) ? R : r
            let pt = CGPoint(x: c.x + cos(a) * rad, y: c.y + sin(a) * rad)
            k == 0 ? p.move(to: pt) : p.addLine(to: pt)
        }
        p.closeSubpath()
        return p
    }

    private func hash(_ i: Int, _ j: Int) -> Int {
        var h = UInt32(truncatingIfNeeded: i &* 73856093 ^ j &* 19349663)
        h ^= h >> 13; h &*= 0x5bd1e995; h ^= h >> 15
        return Int(h % 1000)
    }

    /// 0.8 … 1.2 — hand-glazed variance.
    private func jitter(_ h: Int) -> Double { 0.8 + Double(h % 400) / 1000 }
}

// MARK: - Tessera: the single-tile glyph used for ranks, chips, the rosette.

struct Tessera: View {
    enum Cut { case star, diamond, square }
    var shape: Cut = .star
    var color: Color
    var filled: Bool = true
    var size: CGFloat = Mosaic.Size.tessera

    var body: some View {
        Canvas { ctx, s in
            let c = CGPoint(x: s.width / 2, y: s.height / 2)
            let R = min(s.width, s.height) / 2
            let path: Path = switch shape {
            case .star:    ZelligeBackground.starPath(center: c, R: R, points: 8, innerRatio: 0.7654)
            case .diamond: ZelligeBackground.starPath(center: c, R: R, points: 2, innerRatio: 0.7071, rotation: 0)
            case .square:  Path(roundedRect: CGRect(origin: .zero, size: s).insetBy(dx: R * 0.15, dy: R * 0.15), cornerRadius: R * 0.15)
            }
            if filled { ctx.fill(path, with: .color(color)) }
            else { ctx.stroke(path, with: .color(color), lineWidth: 1) }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

// (Xcode #Preview blocks removed: the CLT swiftc used by ./build.sh cannot
// expand preview macros. Visuals are verified via --render-shot-focus.)
