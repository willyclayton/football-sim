import Foundation

/// Where an entity is at an instant between tracking frames.
public struct EntityState: Sendable, Equatable {
    /// Yards along the field; the offense attacks +x.
    public var x: Double
    /// Yards across the field; +y is the offense's left.
    public var y: Double
    /// Height in yards (the ball only; synthesized, badge Derived).
    public var z: Double
    /// Yards per second, if tracked.
    public var speed: Double?
    /// Direction of motion in degrees clockwise from +y, if tracked.
    public var direction: Double?
    /// Facing in degrees clockwise from +y, if tracked.
    public var facing: Double?
    /// True when this position comes from a filled sensor gap.
    public var filled: Bool
    /// False when there is no position at all.
    public var present: Bool

    public static let absent = EntityState(x: 0, y: 0, z: 0, speed: nil, direction: nil, facing: nil,
                                           filled: false, present: false)
}

/// Turns a play file into positions at any time, for drawing at 60 or 120 fps.
///
/// Players: cubic Hermite through the 10 Hz points, with tangents from the
/// measured speed and direction, so curves bend the way the player was moving
/// and nothing looks steppy. Where direction is missing, straight lines.
/// Ball: follows the play file's segments (tracked, held, flight).
public struct Playback: Sendable {
    public let file: PlayFile
    public static let carryHeight = 1.0

    public init(file: PlayFile) {
        self.file = file
    }

    public var duration: Double { file.duration }
    public var header: PlayHeader { file.header }

    /// Fractional frame index at a time in seconds, clamped to the play.
    public func frame(at time: Double) -> Double {
        min(max(time * file.frameRate, 0), Double(max(file.frameCount - 1, 0)))
    }

    public func time(ofFrame frame: Int) -> Double { file.time(ofFrame: frame) }

    // MARK: Players

    public func state(ofEntity entity: Int, at time: Double) -> EntityState {
        if entity == 0 { return ballState(at: time) }
        return interpolatedState(ofEntity: entity, atFrame: frame(at: time))
    }

    func interpolatedState(ofEntity entity: Int, atFrame f: Double) -> EntityState {
        let i = Int(f.rounded(.down))
        let u = f - Double(i)
        let a = file.record(frame: i, entity: entity)
        guard a.hasPosition else { return .absent }
        if u < 1e-9 || i + 1 >= file.frameCount {
            return Self.state(of: a)
        }
        let b = file.record(frame: i + 1, entity: entity)
        guard b.hasPosition else { return Self.state(of: a) }

        let dt = 1.0 / file.frameRate
        var x: Double
        var y: Double
        if let va = Self.velocity(a), let vb = Self.velocity(b) {
            let h00 = 2 * u * u * u - 3 * u * u + 1
            let h10 = u * u * u - 2 * u * u + u
            let h01 = -2 * u * u * u + 3 * u * u
            let h11 = u * u * u - u * u
            x = h00 * a.x + h10 * va.x * dt + h01 * b.x + h11 * vb.x * dt
            y = h00 * a.y + h10 * va.y * dt + h01 * b.y + h11 * vb.y * dt
        } else {
            x = a.x + (b.x - a.x) * u
            y = a.y + (b.y - a.y) * u
        }
        var s = Self.state(of: a)
        s.x = x
        s.y = y
        if let sa = a.speed, let sb = b.speed { s.speed = sa + (sb - sa) * u }
        if let da = a.direction, let db = b.direction { s.direction = Self.lerpAngle(da, db, u) }
        if let fa = a.facing, let fb = b.facing { s.facing = Self.lerpAngle(fa, fb, u) }
        s.filled = a.isFilled || b.isFilled
        return s
    }

    static func state(of r: Record) -> EntityState {
        EntityState(x: r.x, y: r.y, z: 0, speed: r.speed, direction: r.direction, facing: r.facing,
                    filled: r.isFilled, present: r.hasPosition)
    }

    /// Velocity in yards per second from speed and direction (clockwise from +y).
    static func velocity(_ r: Record) -> (x: Double, y: Double)? {
        guard let s = r.speed, let d = r.direction else { return nil }
        let rad = d * .pi / 180
        return (s * sin(rad), s * cos(rad))
    }

    static func lerpAngle(_ a: Double, _ b: Double, _ u: Double) -> Double {
        var d = (b - a).truncatingRemainder(dividingBy: 360)
        if d > 180 { d -= 360 }
        if d < -180 { d += 360 }
        var out = (a + d * u).truncatingRemainder(dividingBy: 360)
        if out < 0 { out += 360 }
        return out
    }

    // MARK: Ball

    public func segment(containing frame: Int) -> BallSegment? {
        header.ball.segments.first { $0.contains(frame) }
    }

    public func ballState(at time: Double) -> EntityState {
        let f = frame(at: time)
        let i = Int(f.rounded(.down))
        let u = f - Double(i)
        guard let seg = segment(containing: i) else {
            return interpolatedState(ofEntity: 0, atFrame: f)
        }
        if u > 1e-9, i + 1 < file.frameCount, !seg.contains(i + 1), let next = segment(containing: i + 1) {
            // Crossing into the next segment: blend the two endpoints.
            let a = ballPoint(atFrame: Double(i), in: seg)
            let b = ballPoint(atFrame: Double(i + 1), in: next)
            guard a.present, b.present else { return a.present ? a : b }
            var s = a
            s.x = a.x + (b.x - a.x) * u
            s.y = a.y + (b.y - a.y) * u
            s.z = a.z + (b.z - a.z) * u
            return s
        }
        return ballPoint(atFrame: f, in: seg)
    }

    func ballPoint(atFrame f: Double, in seg: BallSegment) -> EntityState {
        switch seg.mode {
        case .held:
            guard let holder = seg.holder, holder > 0, holder < file.entityCount else {
                return interpolatedState(ofEntity: 0, atFrame: f)
            }
            var s = interpolatedState(ofEntity: holder, atFrame: f)
            s.z = Self.carryHeight
            return s
        case .tracked:
            var s = interpolatedState(ofEntity: 0, atFrame: f)
            s.z = seg.z0 ?? 0
            return s
        case .flight:
            var s = interpolatedState(ofEntity: 0, atFrame: f)
            s.z = Self.arcHeight(seg, atFrame: f)
            return s
        }
    }

    /// Height of a ball in flight: the straight line from release to catch plus
    /// a parabola whose apex comes from the flight time (synthesized; badge Derived).
    public static func arcHeight(_ seg: BallSegment, atFrame f: Double) -> Double {
        let span = Double(seg.to - seg.from)
        guard span > 0 else { return seg.z0 ?? 0 }
        let u = min(max((f - Double(seg.from)) / span, 0), 1)
        let z0 = seg.z0 ?? 0
        let z1 = seg.z1 ?? z0
        return z0 + (z1 - z0) * u + 4 * (seg.apex ?? 0) * u * (1 - u)
    }

    // MARK: Clock and events

    /// Seconds left in the quarter at `time`, counting down from the snap
    /// (or for kickoffs from the catch). Nil when the play has no clock.
    public func gameClock(at time: Double) -> Double? {
        guard let start = header.clock.secondsAtStart else { return nil }
        guard let startFrame = header.clock.startFrame else { return Double(start) }
        let elapsed = max(0, time - self.time(ofFrame: startFrame))
        return max(0, Double(start) - elapsed)
    }

    /// "3:10" style; whole seconds round up so 3:10 shows until a full second has run.
    public static func formatClock(_ seconds: Double) -> String {
        let s = Int(seconds.rounded(.up))
        return String(format: "%d:%02d", s / 60, s % 60)
    }

    /// Events whose frame lies in (from, to], for haptics and markers during playback.
    public func events(after from: Double, through to: Double) -> [PlayEvent] {
        let a = frame(at: from)
        let b = frame(at: to)
        guard b > a else { return [] }
        return header.events.filter { Double($0.frame) > a && Double($0.frame) <= b }
    }
}
