import Foundation
import XCTest
@testable import PlaybackCore

/// Tests against the synthetic, made-up fixture written by `python -m all22 fixtures`.
/// The same file is checked by the Python tests, so both sides agree on the format.
final class PlaybackCoreTests: XCTestCase {
    struct Expected: Decodable {
        struct Sample: Decodable {
            let frame: Int
            let entity: Int
            let x: Int
            let y: Int
            let s: Int
            let dir: Int
            let o: Int
            let flags: Int
        }

        struct Segment: Decodable {
            let from: Int
            let to: Int
            let mode: String
            let holder: Int?
        }

        struct BallBlock: Decodable { let segments: [Segment] }

        struct CalloutLabels: Decodable {
            let offense: [String]
            let defense: [String]
            let afterSnap: [String]
        }

        let id: String
        let frames: Int
        let entities: Int
        let samples: [Sample]
        let ball: BallBlock
        let callouts: CalloutLabels
        let status: String
    }

    func fixture(_ name: String) throws -> URL {
        let url = Bundle.module.url(forResource: name, withExtension: nil, subdirectory: "Fixtures")
        return try XCTUnwrap(url, "missing fixture \(name)")
    }

    func loadPlay() throws -> PlayFile {
        try PlayFile(contentsOf: fixture("synthetic-play.a22"))
    }

    func loadExpected() throws -> Expected {
        try JSONDecoder().decode(Expected.self, from: Data(contentsOf: fixture("synthetic-expected.json")))
    }

    func testDecodesHeaderAndFrames() throws {
        let play = try loadPlay()
        let expected = try loadExpected()
        XCTAssertEqual(play.header.id, expected.id)
        XCTAssertEqual(play.header.synthetic, true)
        XCTAssertEqual(play.frameCount, expected.frames)
        XCTAssertEqual(play.entityCount, expected.entities)
        XCTAssertEqual(play.header.checks.status, expected.status)
        XCTAssertTrue(play.header.entities[0].isBall)
        XCTAssertEqual(play.header.callouts.offense.map(\.label), expected.callouts.offense)
        XCTAssertEqual(play.header.callouts.defense.map(\.label), expected.callouts.defense)
        XCTAssertEqual(play.header.callouts.offense.first?.badge, .derived)
    }

    func testRecordsMatchThePythonSide() throws {
        let play = try loadPlay()
        for s in try loadExpected().samples {
            let r = play.record(frame: s.frame, entity: s.entity)
            XCTAssertEqual(Int(r.rawX), s.x, "x at \(s.frame),\(s.entity)")
            XCTAssertEqual(Int(r.rawY), s.y, "y at \(s.frame),\(s.entity)")
            XCTAssertEqual(Int(r.rawSpeed), s.s)
            XCTAssertEqual(Int(r.rawDirection), s.dir)
            XCTAssertEqual(Int(r.rawFacing), s.o)
            XCTAssertEqual(Int(r.flags), s.flags)
        }
    }

    func testFilledRecordsAreFlagged() throws {
        let play = try loadPlay()
        let filled = try loadExpected().samples.filter { $0.flags & Int(Record.flagFilled) != 0 }
        XCTAssertFalse(filled.isEmpty)
        for s in filled {
            XCTAssertTrue(play.record(frame: s.frame, entity: s.entity).isFilled)
        }
    }

    func testBallSegmentsDecode() throws {
        let play = try loadPlay()
        let expected = try loadExpected().ball.segments
        let got = play.header.ball.segments
        XCTAssertEqual(got.count, expected.count)
        for (g, e) in zip(got, expected) {
            XCTAssertEqual(g.from, e.from)
            XCTAssertEqual(g.to, e.to)
            XCTAssertEqual(g.mode.rawValue, e.mode)
            XCTAssertEqual(g.holder, e.holder)
        }
        // Segments tile every frame.
        XCTAssertEqual(got.first?.from, 0)
        XCTAssertEqual(got.last?.to, play.frameCount - 1)
    }

    func testInterpolationPassesThroughEveryFrame() throws {
        let playback = Playback(file: try loadPlay())
        for entity in 1 ..< playback.file.entityCount {
            for frame in stride(from: 0, to: playback.file.frameCount, by: 7) {
                let r = playback.file.record(frame: frame, entity: entity)
                let s = playback.state(ofEntity: entity, at: playback.time(ofFrame: frame))
                XCTAssertEqual(s.x, r.x, accuracy: 1e-9)
                XCTAssertEqual(s.y, r.y, accuracy: 1e-9)
            }
        }
    }

    func testInterpolationIsSmoothBetweenFrames() throws {
        let playback = Playback(file: try loadPlay())
        let receiver = 3
        let kf = playback.header.keyFrames
        let frame = try XCTUnwrap(kf.snap) + 8
        let a = playback.file.record(frame: frame, entity: receiver)
        let b = playback.file.record(frame: frame + 1, entity: receiver)
        let mid = playback.state(ofEntity: receiver, at: (Double(frame) + 0.5) / playback.file.frameRate)
        // A runner at constant speed lands near the straight-line midpoint.
        XCTAssertEqual(mid.x, (a.x + b.x) / 2, accuracy: 0.05)
        XCTAssertEqual(mid.y, (a.y + b.y) / 2, accuracy: 0.05)
    }

    func testBallIsInTheHoldersHands() throws {
        let playback = Playback(file: try loadPlay())
        let held = try XCTUnwrap(playback.header.ball.segments.first { $0.mode == .held })
        let holder = try XCTUnwrap(held.holder)
        let t = playback.time(ofFrame: (held.from + held.to) / 2)
        let ball = playback.ballState(at: t)
        let player = playback.state(ofEntity: holder, at: t)
        XCTAssertEqual(ball.x, player.x, accuracy: 1e-9)
        XCTAssertEqual(ball.y, player.y, accuracy: 1e-9)
        XCTAssertEqual(ball.z, Playback.carryHeight, accuracy: 1e-9)
    }

    func testThrowArcsAboveItsEndpoints() throws {
        let playback = Playback(file: try loadPlay())
        let flight = try XCTUnwrap(playback.header.ball.segments.last { $0.mode == .flight })
        let midFrame = Double(flight.from + flight.to) / 2
        let peak = Playback.arcHeight(flight, atFrame: midFrame)
        XCTAssertGreaterThan(peak, max(flight.z0 ?? 0, flight.z1 ?? 0))
        XCTAssertEqual(Playback.arcHeight(flight, atFrame: Double(flight.from)), flight.z0 ?? 0, accuracy: 1e-9)
        XCTAssertEqual(Playback.arcHeight(flight, atFrame: Double(flight.to)), flight.z1 ?? 0, accuracy: 1e-9)
    }

    func testGameClockCountsDownFromTheSnap() throws {
        let playback = Playback(file: try loadPlay())
        let start = try XCTUnwrap(playback.header.clock.startFrame)
        let seconds = try XCTUnwrap(playback.header.clock.secondsAtStart)
        XCTAssertEqual(playback.gameClock(at: 0), Double(seconds))
        let later = playback.time(ofFrame: start) + 1.25
        XCTAssertEqual(try XCTUnwrap(playback.gameClock(at: later)), Double(seconds) - 1.25, accuracy: 1e-9)
        XCTAssertEqual(Playback.formatClock(450), "7:30")
        XCTAssertEqual(Playback.formatClock(448.75), "7:29")
        XCTAssertEqual(Playback.formatClock(9.2), "0:10")
    }

    func testEventsBetweenTimes() throws {
        let playback = Playback(file: try loadPlay())
        let all = playback.events(after: -1, through: playback.duration)
        XCTAssertEqual(all.count, playback.header.events.count)
        XCTAssertTrue(all.contains { $0.haptic })
    }

    func testCatalogLoads() throws {
        let plays = try Catalog.load(from: fixture("synthetic-catalog.sqlite"))
        XCTAssertEqual(plays.count, 1)
        let p = try XCTUnwrap(plays.first)
        XCTAssertEqual(p.id, "2000010100-1")
        XCTAssertEqual(p.offense, "AWY")
        XCTAssertEqual(p.personnel, "11 personnel")
        XCTAssertEqual(p.defensivePackage, "Nickel")
        XCTAssertEqual(p.yards, 17)
        XCTAssertEqual(p.status, "ship")
        XCTAssertFalse(p.awaitingReview)
    }

    func testRejectsGarbage() {
        XCTAssertThrowsError(try PlayFile(data: Data(repeating: 0, count: 64))) { error in
            XCTAssertEqual(error as? PlayFileError, .badMagic)
        }
        XCTAssertThrowsError(try PlayFile(data: Data("A22P".utf8))) { error in
            XCTAssertEqual(error as? PlayFileError, .truncated)
        }
    }

    func testFieldNumbers() {
        XCTAssertEqual(Field.yardNumber(atX: 60), 50)
        XCTAssertEqual(Field.yardNumber(atX: 20), 10)
        XCTAssertEqual(Field.yardNumber(atX: 100), 10)
        XCTAssertNil(Field.yardNumber(atX: 25))
        XCTAssertEqual(Units.mph(10), 20.4545, accuracy: 1e-3)
    }
}
