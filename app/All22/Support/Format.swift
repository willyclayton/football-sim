import PlaybackCore
import SwiftUI

enum Format {
    static func quarterName(_ q: Int?) -> String {
        switch q {
        case 1: return "1st quarter"
        case 2: return "2nd quarter"
        case 3: return "3rd quarter"
        case 4: return "4th quarter"
        case 5: return "Overtime"
        default: return "Quarter ?"
        }
    }

    static func quarterShort(_ q: Int?) -> String {
        switch q {
        case 1: return "1st"
        case 2: return "2nd"
        case 3: return "3rd"
        case 4: return "4th"
        case 5: return "OT"
        default: return "-"
        }
    }

    static func ordinalDown(_ d: Int?) -> String? {
        switch d {
        case 1: return "1st"
        case 2: return "2nd"
        case 3: return "3rd"
        case 4: return "4th"
        default: return nil
        }
    }

    static func downAndDistance(down: Int?, toGo: Int?, goalToGo: Bool) -> String? {
        guard let d = ordinalDown(down) else { return nil }
        if goalToGo { return "\(d) & Goal" }
        guard let toGo else { return d }
        return "\(d) & \(toGo)"
    }

    static func clock(_ seconds: Int?) -> String {
        guard let seconds else { return "" }
        return String(format: "%d:%02d", seconds / 60, seconds % 60)
    }

    static func signed(_ v: Double, digits: Int = 2) -> String {
        String(format: "%+.\(digits)f", v)
    }
}

extension Color {
    /// "#RRGGBB" from the play file's team colors.
    init(hex: String) {
        var s = hex.trimmingCharacters(in: .whitespaces)
        if s.hasPrefix("#") { s.removeFirst() }
        let value = UInt64(s, radix: 16) ?? 0x555555
        self.init(.sRGB,
                  red: Double((value >> 16) & 0xFF) / 255,
                  green: Double((value >> 8) & 0xFF) / 255,
                  blue: Double(value & 0xFF) / 255,
                  opacity: 1)
    }
}

extension Badge {
    var color: Color {
        switch self {
        case .tracked: return .green
        case .official: return .blue
        case .derived: return .purple
        case .charted: return .orange
        case .model: return .gray
        case .animated: return .pink
        case .simulated: return .red
        case .unknown: return .secondary
        }
    }

    var letter: String { String(title.prefix(1)) }
}
