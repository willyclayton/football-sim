import Foundation

/// Field geometry in yards, in the play file's normalized coordinates.
public enum Field {
    public static let length = 120.0
    public static let width = 53.3
    public static let goalLineLeft = 10.0
    public static let goalLineRight = 110.0
    /// NFL hash marks: 70 ft 9 in from each sideline.
    public static let hashFromSideline = 23.58
    public static var hashes: (Double, Double) { (hashFromSideline, width - hashFromSideline) }
    /// Yard-line number shown at an x position ("50", "40", ..., or nil off the 10s).
    public static func yardNumber(atX x: Double) -> Int? {
        let yards = Int((x - goalLineLeft).rounded())
        guard yards > 0, yards < 100, yards % 10 == 0 else { return nil }
        return yards <= 50 ? yards : 100 - yards
    }
}

public enum Units {
    public static let metersPerYard = 0.9144
    /// Yards per second to miles per hour.
    public static func mph(_ yardsPerSecond: Double) -> Double { yardsPerSecond * 3600 / 1760 }
}
