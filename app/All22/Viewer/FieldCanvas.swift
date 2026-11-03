import PlaybackCore
import SwiftUI

/// Everything one drawn frame needs, captured as plain values.
struct FrameSnapshot {
    struct Player {
        let index: Int
        let x: Double
        let y: Double
        let speed: Double?
        let heading: Double?
        let filled: Bool
        let fill: Color
        let ring: Color
        let text: Color
        let label: String  // last name, shown above the dot when names are on
        let jerseyText: String
    }

    struct Trail {
        let points: [CGPoint]  // field yards
        let color: Color
    }

    struct Separation {
        let from: CGPoint
        let to: CGPoint
        let yards: Double
    }

    var transform: FieldTransform
    var players: [Player]
    var ball: EntityState
    var trails: [Trail]
    var ballPath: [CGPoint]
    var overlays: Overlays
    var selected: Int?
    var separation: Separation?
}

struct TeamPaint {
    let fill: Color
    let ring: Color
    let text: Color

    /// Home in team colors; visitors in road whites trimmed with team color.
    init(team: Team, home: Bool) {
        if home {
            fill = Color(hex: team.primaryColor)
            ring = Color(hex: team.secondaryColor)
            text = Color(hex: team.textColor)
        } else {
            fill = .white
            ring = Color(hex: team.primaryColor)
            text = Color(hex: team.primaryColor)
        }
    }
}

/// The static field: grass, lines, numbers, hashes, end zones.
struct FieldBackground: View, Equatable {
    let transform: FieldTransform
    let leftEndZone: Team
    let rightEndZone: Team
    let losX: Double?
    let lineToGainX: Double?
    let showLines: Bool

    static func == (a: FieldBackground, b: FieldBackground) -> Bool {
        a.transform == b.transform && a.losX == b.losX && a.lineToGainX == b.lineToGainX
            && a.showLines == b.showLines && a.leftEndZone == b.leftEndZone && a.rightEndZone == b.rightEndZone
    }

    var body: some View {
        Canvas { ctx, _ in
            let t = transform
            ctx.fill(Path(CGRect(origin: .zero, size: t.size)), with: .color(Color(red: 0.07, green: 0.11, blue: 0.08)))

            // Grass, striped every 5 yards.
            for i in 0 ..< 24 {
                let x0 = Double(i) * 5
                let rect = rectFor(x0: x0, x1: x0 + 5, y0: 0, y1: Field.width)
                let even = i % 2 == 0
                ctx.fill(Path(rect), with: .color(even ? Color(red: 0.16, green: 0.45, blue: 0.20)
                                                       : Color(red: 0.14, green: 0.41, blue: 0.18)))
            }
            // End zones in team colors, with the team code (no logos or wordmarks).
            for (x0, team) in [(0.0, leftEndZone), (Field.goalLineRight, rightEndZone)] {
                let rect = rectFor(x0: x0, x1: x0 + 10, y0: 0, y1: Field.width)
                ctx.fill(Path(rect), with: .color(Color(hex: team.primaryColor).opacity(0.85)))
                var label = ctx
                label.translateBy(x: rect.midX, y: rect.midY)
                label.rotate(by: .degrees(x0 == 0 ? -90 : 90))
                label.draw(Text(team.abbr).font(.system(size: t.length(5), weight: .black))
                    .foregroundStyle(Color(hex: team.textColor).opacity(0.8)), at: .zero)
            }
            // Yard lines.
            for yard in stride(from: 10, through: 110, by: 5) {
                let x = Double(yard)
                let width: CGFloat = (yard == 10 || yard == 110) ? max(2, t.length(0.33)) : max(1, t.length(0.14))
                ctx.stroke(line(x0: x, y0: 0, x1: x, y1: Field.width), with: .color(.white.opacity(0.85)), lineWidth: width)
            }
            // Hash marks and sideline ticks, every yard.
            let (h1, h2) = Field.hashes
            for yard in 11 ... 109 where yard % 5 != 0 {
                let x = Double(yard)
                for (y0, y1) in [(0.3, 1.0), (h1 - 0.35, h1 + 0.35), (h2 - 0.35, h2 + 0.35), (Field.width - 1.0, Field.width - 0.3)] {
                    ctx.stroke(line(x0: x, y0: y0, x1: x, y1: y1), with: .color(.white.opacity(0.7)), lineWidth: max(1, t.length(0.12)))
                }
            }
            // Numbers.
            for yard in stride(from: 20, through: 100, by: 10) {
                guard let n = Field.yardNumber(atX: Double(yard)) else { continue }
                for y in [12.0, Field.width - 12.0] {
                    ctx.draw(Text("\(n)").font(.system(size: t.length(2.2), weight: .bold))
                        .foregroundStyle(.white.opacity(0.8)), at: t.point(Double(yard), y))
                }
            }
            // Boundary.
            ctx.stroke(Path(rectFor(x0: 0, x1: Field.length, y0: 0, y1: Field.width)), with: .color(.white), lineWidth: max(2, t.length(0.33)))

            if showLines {
                if let los = losX {
                    ctx.stroke(line(x0: los, y0: 0, x1: los, y1: Field.width),
                               with: .color(Color(red: 0.25, green: 0.55, blue: 1.0)), lineWidth: max(2, t.length(0.25)))
                }
                if let ltg = lineToGainX {
                    ctx.stroke(line(x0: ltg, y0: 0, x1: ltg, y1: Field.width),
                               with: .color(.yellow), lineWidth: max(2, t.length(0.25)))
                }
            }
        }
    }

    private func rectFor(x0: Double, x1: Double, y0: Double, y1: Double) -> CGRect {
        let a = transform.point(x0, y1)
        let b = transform.point(x1, y0)
        return CGRect(x: a.x, y: a.y, width: b.x - a.x, height: b.y - a.y)
    }

    private func line(x0: Double, y0: Double, x1: Double, y1: Double) -> Path {
        Path { p in
            p.move(to: transform.point(x0, y0))
            p.addLine(to: transform.point(x1, y1))
        }
    }
}

/// Players, ball and overlays for one instant.
struct PlayersLayer: View {
    let snapshot: FrameSnapshot

    var body: some View {
        Canvas { ctx, _ in
            let s = snapshot
            let t = s.transform

            if s.overlays.routes {
                for trail in s.trails where trail.points.count > 1 {
                    var path = Path()
                    path.move(to: t.point(trail.points[0].x, trail.points[0].y))
                    for p in trail.points.dropFirst() { path.addLine(to: t.point(p.x, p.y)) }
                    ctx.stroke(path, with: .color(trail.color.opacity(0.75)),
                               style: StrokeStyle(lineWidth: max(1.5, t.length(0.22)), lineCap: .round, lineJoin: .round))
                }
            }
            if s.overlays.ballPath, s.ballPath.count > 1 {
                var path = Path()
                path.move(to: t.point(s.ballPath[0].x, s.ballPath[0].y))
                for p in s.ballPath.dropFirst() { path.addLine(to: t.point(p.x, p.y)) }
                ctx.stroke(path, with: .color(Color(red: 0.95, green: 0.75, blue: 0.4)),
                           style: StrokeStyle(lineWidth: max(1, t.length(0.15)), dash: [4, 4]))
            }
            if s.overlays.separation, let sep = s.separation {
                let a = t.point(sep.from.x, sep.from.y)
                let b = t.point(sep.to.x, sep.to.y)
                ctx.stroke(Path { p in p.move(to: a); p.addLine(to: b) }, with: .color(.white),
                           style: StrokeStyle(lineWidth: 1.5, dash: [3, 3]))
                ctx.draw(Text(String(format: "%.1f yds", sep.yards)).font(.caption2.bold())
                    .foregroundStyle(.white), at: CGPoint(x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 10))
            }

            let radius = max(5, t.length(0.95))
            for p in s.players {
                let c = t.point(p.x, p.y)
                let disc = CGRect(x: c.x - radius, y: c.y - radius, width: radius * 2, height: radius * 2)
                if p.index == s.selected {
                    ctx.fill(Path(ellipseIn: disc.insetBy(dx: -radius * 0.6, dy: -radius * 0.6)),
                             with: .color(.yellow.opacity(0.45)))
                }
                if let heading = p.heading {
                    let rad = heading * .pi / 180
                    // Screen y points down, so +y in the field is -y on screen.
                    let tip = CGPoint(x: c.x + sin(rad) * radius * 1.6, y: c.y - cos(rad) * radius * 1.6)
                    ctx.stroke(Path { q in q.move(to: c); q.addLine(to: tip) }, with: .color(p.ring),
                               lineWidth: max(1.5, radius * 0.3))
                }
                ctx.fill(Path(ellipseIn: disc), with: .color(p.fill))
                if p.filled {
                    ctx.stroke(Path(ellipseIn: disc), with: .color(.white),
                               style: StrokeStyle(lineWidth: max(1, radius * 0.22), dash: [2, 2]))
                } else {
                    ctx.stroke(Path(ellipseIn: disc), with: .color(p.ring), lineWidth: max(1, radius * 0.22))
                }
                if s.overlays.names {
                    ctx.draw(Text(p.label).font(.system(size: max(8, radius * 0.8), weight: .semibold))
                        .foregroundStyle(.white), at: CGPoint(x: c.x, y: c.y - radius * 1.8))
                }
                let number = p.jerseyText
                ctx.draw(Text(number).font(.system(size: radius * (number.count > 1 ? 0.95 : 1.1), weight: .bold))
                    .foregroundStyle(p.text), at: c)
                if s.overlays.speeds, let speed = p.speed, speed > 4.5 {
                    ctx.draw(Text("\(Int(Units.mph(speed).rounded()))").font(.system(size: max(8, radius * 0.75), weight: .semibold))
                        .foregroundStyle(.white), at: CGPoint(x: c.x, y: c.y + radius * 1.7))
                }
            }

            // Ball: a shadow on the grass, the ball lifted by its height.
            if s.ball.present {
                let g = t.point(s.ball.x, s.ball.y)
                let lift = t.length(s.ball.z * 0.6)
                let size = max(4, t.length(0.55 + s.ball.z * 0.05))
                ctx.fill(Path(ellipseIn: CGRect(x: g.x - size * 0.6, y: g.y - size * 0.35, width: size * 1.2, height: size * 0.7)),
                         with: .color(.black.opacity(0.35)))
                let b = CGPoint(x: g.x, y: g.y - lift)
                ctx.fill(Path(ellipseIn: CGRect(x: b.x - size * 0.75, y: b.y - size * 0.5, width: size * 1.5, height: size)),
                         with: .color(Color(red: 0.55, green: 0.29, blue: 0.12)))
                ctx.stroke(Path(ellipseIn: CGRect(x: b.x - size * 0.75, y: b.y - size * 0.5, width: size * 1.5, height: size)),
                           with: .color(.white.opacity(0.9)), lineWidth: 1)
            }
        }
    }
}
