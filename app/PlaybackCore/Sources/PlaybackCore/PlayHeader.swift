import Foundation

/// The JSON header of a play file. Field-for-field mirror of docs/play-format.md.
public struct PlayHeader: Codable, Sendable {
    public let format: String
    public let version: Int
    public let id: String
    public let synthetic: Bool?
    public let edition: EditionInfo
    public let game: GameInfo
    public let situation: Situation
    public let outcome: Outcome
    public let frames: FramesInfo
    public let entities: [PlayEntity]
    public let events: [PlayEvent]
    public let keyFrames: KeyFrames
    public let clock: ClockInfo
    public let ball: BallInfo
    public let carrier: Int?
    public let callouts: Callouts
    public let checks: Checks
    public let review: ReviewInfo
    public let stats: PlayStats
    public let provenance: Provenance?
}

public struct EditionInfo: Codable, Sendable {
    public let id: String
    public let name: String?
}

public struct Team: Codable, Sendable, Hashable {
    public let abbr: String
    public let name: String
    public let primaryColor: String
    public let secondaryColor: String
    public let textColor: String
}

public struct GameInfo: Codable, Sendable {
    public let id: String
    public let season: Int
    public let week: Int
    public let date: String?
    public let home: Team
    public let away: Team

    public func team(_ side: String?) -> Team? {
        switch side {
        case "home": return home
        case "away": return away
        default: return nil
        }
    }
}

public struct Score: Codable, Sendable, Hashable {
    public let home: Int?
    public let away: Int?
}

public struct Situation: Codable, Sendable {
    public let quarter: Int?
    public let clockSeconds: Int?
    public let down: Int?
    public let yardsToGo: Int?
    public let goalToGo: Bool?
    public let possession: String?
    /// "home" or "away": the team on offense (for kicks, the kicking team).
    public let offense: String?
    public let yardline: String?
    public let losX: Double?
    public let losSource: String?
    public let lineToGainX: Double?
    public let scoreBefore: Score?
}

public struct Outcome: Codable, Sendable {
    public let description: String?
    public let type: String?
    public let result: String?
    public let yards: Double?
    public let touchdown: Bool?
    public let scoreAfter: Score?
    public let epa: Double?
    public let wpa: Double?
    public let winProbability: Double?
}

public struct FramesInfo: Codable, Sendable {
    public let count: Int
    public let rate: Int
    public let encoding: String
    public let recordSize: Int
    public let sourceStartFrame: Int?
    public let orientation: Bool?
}

public struct PlayEntity: Codable, Sendable, Hashable {
    public let kind: String
    public let team: String?
    public let side: String?
    public let nflId: Int?
    public let name: String?
    public let jersey: Int?
    public let position: String?
    public let group: String?

    public var isBall: Bool { kind == "ball" }
    public var isOffense: Bool { side == "offense" }
}

public struct PlayEvent: Codable, Sendable, Hashable {
    public let frame: Int
    public let name: String
    public let label: String
    public let marker: Bool
    public let haptic: Bool
}

public struct KeyFrames: Codable, Sendable {
    public let start: Int?
    public let snap: Int?
    public let kick: Int?
    public let handoff: Int?
    public let throwFrame: Int?
    public let arrival: Int?
    public let catchFrame: Int?
    public let outcome: Int?
    public let received: Int?
    public let contact: Int?
    public let tackle: Int?
    public let whistle: Int?
    public let end: Int?

    enum CodingKeys: String, CodingKey {
        case start, snap, kick, handoff, arrival, outcome, received, contact, tackle, whistle, end
        case throwFrame = "throw"
        case catchFrame = "catch"
    }
}

public struct ClockInfo: Codable, Sendable {
    /// Frame at which the game clock starts running; nil when it doesn't run during the play.
    public let startFrame: Int?
    public let secondsAtStart: Int?
}

public struct BallInfo: Codable, Sendable {
    public let segments: [BallSegment]
}

public struct BallSegment: Codable, Sendable, Hashable {
    public enum Mode: String, Codable, Sendable {
        case tracked, held, flight

        public init(from decoder: Decoder) throws {
            let raw = try decoder.singleValueContainer().decode(String.self)
            self = Mode(rawValue: raw) ?? .tracked
        }
    }

    public let from: Int
    public let to: Int
    public let mode: Mode
    public let holder: Int?
    public let z0: Double?
    public let z1: Double?
    public let apex: Double?

    public func contains(_ frame: Int) -> Bool { frame >= from && frame <= to }
}

/// Where each on-screen fact comes from. See the badge table in docs/play-format.md.
public enum Badge: String, Codable, Sendable, CaseIterable {
    case tracked, official, derived, charted, model, animated, simulated, unknown

    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Badge(rawValue: raw) ?? .unknown
    }

    public var title: String {
        switch self {
        case .tracked: return "Tracked"
        case .official: return "Official"
        case .derived: return "Derived"
        case .charted: return "Charted"
        case .model: return "Model"
        case .animated: return "Animated"
        case .simulated: return "Simulated"
        case .unknown: return "Unknown"
        }
    }

    public var meaning: String {
        switch self {
        case .tracked: return "NFL Next Gen Stats sensor data"
        case .official: return "NFL play-by-play"
        case .derived: return "Fixed rules applied to tracked positions"
        case .charted: return "Coded by human charters; a judgment call"
        case .model: return "Statistical model estimate"
        case .animated: return "Body poses added by the app"
        case .simulated: return "Live-mode estimate, never in replays"
        case .unknown: return "Source not recognized"
        }
    }

    /// True when the fact can be verified exactly against an official source.
    public var verifiable: Bool {
        switch self {
        case .tracked, .official, .derived: return true
        default: return false
        }
    }
}

public struct Callout: Codable, Sendable, Hashable, Identifiable {
    public let key: String
    public let label: String
    public let badge: Badge
    public let missing: Bool
    public let detail: String?
    public let source: String?

    public var id: String { key + "|" + label }
}

public struct Callouts: Codable, Sendable {
    public let offense: [Callout]
    public let defense: [Callout]
    public let afterSnap: [Callout]
}

public struct CheckResult: Codable, Sendable, Hashable, Identifiable {
    public let id: String
    public let name: String
    public let kind: String
    public let result: String
    public let detail: String
}

public struct Checks: Codable, Sendable {
    public let status: String
    public let hard: [CheckResult]
    public let soft: [CheckResult]
    public let notes: [String]
}

public struct ReviewInfo: Codable, Sendable {
    public let status: String
    public let date: String?
    public let note: String?
}

public struct PlayStats: Codable, Sendable {
    public let duration: Double?
    public let topSpeedMph: Double?
    public let topSpeedName: String?
    public let airYards: Double?
    public let airDownfield: Double?
}

public struct Provenance: Codable, Sendable {
    public let pipelineVersion: String?
    public let sources: [String: String]?
    public let flipped: Bool?
    public let direction: String?
}
