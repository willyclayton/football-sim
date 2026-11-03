import CoreGraphics
import Foundation
import Observation
import PlaybackCore

enum CameraMode: String, CaseIterable, Identifiable {
    case play = "Play"
    case fullField = "Full field"
    case follow = "Follow ball"
    case free = "Free"

    var id: String { rawValue }

    var symbol: String {
        switch self {
        case .play: return "viewfinder"
        case .fullField: return "rectangle.expand.vertical"
        case .follow: return "scope"
        case .free: return "hand.draw"
        }
    }
}

struct Overlays: Equatable {
    var routes = true
    var ballPath = true
    var lines = true
    var names = false
    var speeds = false
    var separation = true
    var chipsAfterSnap = false
}

/// Playback state for one play. Time is derived from the clock rather than
/// stepped, so drawing at 60 or 120 fps always shows true speed.
@MainActor
@Observable
final class ViewerModel {
    let playback: Playback
    let playExtent: CGRect

    private(set) var isPlaying = false
    private(set) var rate: Double = 1
    var loop = false
    var camera: CameraMode = .play
    var overlays = Overlays()
    var selected: Int?
    var followed: Int?
    var freeRect: CGRect?
    var showInfo = false
    private(set) var hapticTick = 0

    private var anchorTime: Double = 0
    private var anchorDate = Date()
    private var lastTickTime: Double = 0

    static let rates: [Double] = [0.25, 0.5, 1, 1.5, 2]

    init(playback: Playback) {
        self.playback = playback
        self.playExtent = ViewerModel.extent(of: playback)
    }

    var duration: Double { playback.duration }
    var snapTime: Double? { playback.header.keyFrames.snap.map { playback.time(ofFrame: $0) } }

    func time(at date: Date) -> Double {
        guard isPlaying else { return anchorTime }
        let t = anchorTime + date.timeIntervalSince(anchorDate) * rate
        if loop, duration > 0 {
            return t.truncatingRemainder(dividingBy: duration)
        }
        return min(t, duration)
    }

    func togglePlay() {
        isPlaying ? pause() : play()
    }

    func play() {
        if anchorTime >= duration - 1e-6 { anchorTime = 0 }
        anchorDate = Date()
        lastTickTime = anchorTime
        isPlaying = true
    }

    func pause() {
        anchorTime = time(at: Date())
        isPlaying = false
    }

    func seek(to t: Double) {
        anchorTime = min(max(t, 0), duration)
        anchorDate = Date()
        lastTickTime = anchorTime
    }

    func step(frames: Int) {
        pause()
        let f = (playback.frame(at: anchorTime)).rounded() + Double(frames)
        seek(to: f / playback.file.frameRate)
    }

    func setRate(_ r: Double) {
        let now = Date()
        anchorTime = time(at: now)
        anchorDate = now
        rate = r
    }

    /// Housekeeping after each drawn frame: stop at the end, keep the loop's
    /// anchor fresh, and fire haptics for the catch and the tackle.
    func tick(at date: Date) {
        guard isPlaying else { return }
        let raw = anchorTime + date.timeIntervalSince(anchorDate) * rate
        let t = time(at: date)
        if t < lastTickTime {  // wrapped around the loop
            fireHaptics(from: lastTickTime, to: duration)
            fireHaptics(from: -1, to: t)
        } else {
            fireHaptics(from: lastTickTime, to: t)
        }
        lastTickTime = t
        if raw >= duration {
            if loop {
                anchorTime = t
                anchorDate = date
            } else {
                anchorTime = duration
                isPlaying = false
            }
        }
    }

    private func fireHaptics(from a: Double, to b: Double) {
        if playback.events(after: a, through: b).contains(where: { $0.haptic }) {
            hapticTick += 1
        }
    }

    /// Everything that happens in the play, padded: the default camera frame.
    static func extent(of playback: Playback) -> CGRect {
        var minX = Double.infinity, maxX = -Double.infinity
        var minY = Double.infinity, maxY = -Double.infinity
        let file = playback.file
        for f in stride(from: 0, to: file.frameCount, by: 2) {
            for e in 0 ..< file.entityCount {
                let r = file.record(frame: f, entity: e)
                guard r.hasPosition else { continue }
                minX = min(minX, r.x)
                maxX = max(maxX, r.x)
                minY = min(minY, r.y)
                maxY = max(maxY, r.y)
            }
        }
        guard minX.isFinite else { return CGRect(x: 0, y: 0, width: Field.length, height: Field.width) }
        let pad = 4.0
        var rect = CGRect(x: minX - pad, y: minY - pad, width: maxX - minX + 2 * pad, height: maxY - minY + 2 * pad)
        if rect.width < 30 {
            rect = rect.insetBy(dx: -(30 - rect.width) / 2, dy: 0)
        }
        return rect
    }

    // MARK: Per-player stats for the player card

    struct PlayerStats {
        let topSpeedMph: Double
        let distance: Double
    }

    func stats(forEntity e: Int, through time: Double) -> PlayerStats {
        let kf = playback.header.keyFrames
        let start = kf.snap ?? kf.kick ?? 0
        let end = min(Int(playback.frame(at: time)), kf.whistle ?? (playback.file.frameCount - 1))
        var top = 0.0
        var dist = 0.0
        if end > start {
            var last = playback.file.record(frame: start, entity: e)
            for f in start ... end {
                let r = playback.file.record(frame: f, entity: e)
                if let s = r.speed { top = max(top, s) }
                if r.hasPosition, last.hasPosition, f > start {
                    dist += hypot(r.x - last.x, r.y - last.y)
                }
                last = r
            }
        }
        return PlayerStats(topSpeedMph: Units.mph(top), distance: dist)
    }
}
