import Foundation
import SQLite3

/// One row of the bundled catalog (catalog.sqlite, written by pipeline/all22/catalog.py).
public struct PlaySummary: Sendable, Hashable, Identifiable {
    public let id: String
    public let file: String
    public let edition: String
    public let season: Int
    public let week: Int
    public let gameId: String
    public let playId: Int
    public let gameDate: String?
    public let home: String
    public let away: String
    public let offense: String?
    public let defense: String?
    public let quarter: Int?
    public let clock: Int?
    public let down: Int?
    public let yardsToGo: Int?
    public let yardline: String?
    public let homeScore: Int?
    public let awayScore: Int?
    public let playType: String?
    public let result: String?
    public let yards: Int?
    public let touchdown: Bool
    public let description: String?
    public let epa: Double?
    public let wpa: Double?
    public let personnel: String?
    public let formation: String?
    public let receiverSet: String?
    public let defensivePackage: String?
    public let coverage: String?
    public let topSpeedMph: Double?
    public let topSpeedName: String?
    public let airYards: Double?
    public let duration: Double?
    /// "ship", or "flagged" while awaiting video review.
    public let status: String
    public let flags: String?
    public let reviewedOn: String?

    public var awaitingReview: Bool { status == "flagged" }
}

public enum CatalogError: Error, CustomStringConvertible {
    case open(String)
    case query(String)

    public var description: String {
        switch self {
        case .open(let m): return "Could not open the play catalog: \(m)"
        case .query(let m): return "Could not read the play catalog: \(m)"
        }
    }
}

public enum Catalog {
    static let columns = [
        "id", "file", "edition", "season", "week", "game_id", "play_id", "game_date",
        "home", "away", "offense", "defense", "quarter", "clock", "down", "yards_to_go",
        "yardline", "home_score", "away_score", "play_type", "result", "yards", "touchdown",
        "description", "epa", "wpa", "personnel", "formation", "receiver_set", "package",
        "coverage", "top_speed_mph", "top_speed_name", "air_yards", "duration", "status",
        "flags", "reviewed_on",
    ]

    /// Every play in the catalog, in game order.
    public static func load(from url: URL) throws -> [PlaySummary] {
        var db: OpaquePointer?
        let flags = SQLITE_OPEN_READONLY | SQLITE_OPEN_URI
        let uri = url.absoluteString + "?immutable=1"
        guard sqlite3_open_v2(uri, &db, flags, nil) == SQLITE_OK, let db else {
            let message = db.map { String(cString: sqlite3_errmsg($0)) } ?? "unknown error"
            sqlite3_close(db)
            throw CatalogError.open(message)
        }
        defer { sqlite3_close(db) }

        let sql = "SELECT \(columns.joined(separator: ", ")) FROM plays "
            + "ORDER BY season, week, game_id, quarter, clock DESC, play_id"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK, let stmt else {
            throw CatalogError.query(String(cString: sqlite3_errmsg(db)))
        }
        defer { sqlite3_finalize(stmt) }

        var out: [PlaySummary] = []
        while true {
            let rc = sqlite3_step(stmt)
            if rc == SQLITE_DONE { break }
            guard rc == SQLITE_ROW else { throw CatalogError.query(String(cString: sqlite3_errmsg(db))) }
            let r = Row(stmt: stmt)
            out.append(PlaySummary(
                id: r.text(0) ?? "", file: r.text(1) ?? "", edition: r.text(2) ?? "",
                season: r.int(3) ?? 0, week: r.int(4) ?? 0, gameId: r.text(5) ?? "",
                playId: r.int(6) ?? 0, gameDate: r.text(7), home: r.text(8) ?? "",
                away: r.text(9) ?? "", offense: r.text(10), defense: r.text(11),
                quarter: r.int(12), clock: r.int(13), down: r.int(14), yardsToGo: r.int(15),
                yardline: r.text(16), homeScore: r.int(17), awayScore: r.int(18),
                playType: r.text(19), result: r.text(20), yards: r.int(21),
                touchdown: (r.int(22) ?? 0) != 0, description: r.text(23), epa: r.double(24),
                wpa: r.double(25), personnel: r.text(26), formation: r.text(27),
                receiverSet: r.text(28), defensivePackage: r.text(29), coverage: r.text(30),
                topSpeedMph: r.double(31), topSpeedName: r.text(32), airYards: r.double(33),
                duration: r.double(34), status: r.text(35) ?? "ship", flags: r.text(36),
                reviewedOn: r.text(37)
            ))
        }
        return out
    }

    private struct Row {
        let stmt: OpaquePointer

        func isNull(_ i: Int32) -> Bool { sqlite3_column_type(stmt, i) == SQLITE_NULL }

        func text(_ i: Int32) -> String? {
            guard !isNull(i), let c = sqlite3_column_text(stmt, i) else { return nil }
            return String(cString: c)
        }

        func int(_ i: Int32) -> Int? {
            isNull(i) ? nil : Int(sqlite3_column_int64(stmt, i))
        }

        func double(_ i: Int32) -> Double? {
            isNull(i) ? nil : sqlite3_column_double(stmt, i)
        }
    }
}
