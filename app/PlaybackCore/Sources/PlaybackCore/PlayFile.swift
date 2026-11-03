import Foundation

public enum PlayFileError: Error, Equatable, CustomStringConvertible {
    case badMagic
    case unsupportedVersion(Int)
    case truncated
    case badHeader(String)
    case badFrames(String)

    public var description: String {
        switch self {
        case .badMagic: return "Not an All-22 play file"
        case .unsupportedVersion(let v): return "Play file version \(v) is newer than this app"
        case .truncated: return "Play file is truncated"
        case .badHeader(let why): return "Play header could not be read: \(why)"
        case .badFrames(let why): return "Play frames could not be read: \(why)"
        }
    }
}

/// One packed tracking record: the source's own precision, losslessly.
public struct Record: Sendable, Equatable {
    public static let missingXY = Int16.min
    public static let missingU16 = UInt16.max

    public static let flagMissing: UInt16 = 1
    public static let flagFilled: UInt16 = 2
    public static let flagNoDirection: UInt16 = 4
    public static let flagNoFacing: UInt16 = 8
    public static let flagNoSpeed: UInt16 = 16

    public var rawX: Int16
    public var rawY: Int16
    public var rawSpeed: UInt16
    public var rawDirection: UInt16
    public var rawFacing: UInt16
    public var flags: UInt16

    public init(rawX: Int16, rawY: Int16, rawSpeed: UInt16, rawDirection: UInt16, rawFacing: UInt16, flags: UInt16) {
        self.rawX = rawX
        self.rawY = rawY
        self.rawSpeed = rawSpeed
        self.rawDirection = rawDirection
        self.rawFacing = rawFacing
        self.flags = flags
    }

    public var hasPosition: Bool { rawX != Self.missingXY && rawY != Self.missingXY }
    /// Yards along the field (offense attacks +x).
    public var x: Double { Double(rawX) / 100 }
    /// Yards across the field (+y is the offense's left, looking downfield).
    public var y: Double { Double(rawY) / 100 }
    /// Yards per second.
    public var speed: Double? { rawSpeed == Self.missingU16 ? nil : Double(rawSpeed) / 100 }
    /// Direction of motion, degrees clockwise from +y.
    public var direction: Double? { rawDirection == Self.missingU16 ? nil : Double(rawDirection) / 100 }
    /// Facing, degrees clockwise from +y (not in every edition).
    public var facing: Double? { rawFacing == Self.missingU16 ? nil : Double(rawFacing) / 100 }
    public var isFilled: Bool { flags & Self.flagFilled != 0 }
}

/// A decoded `.a22` play file (format: docs/play-format.md).
public struct PlayFile: Sendable {
    public static let magic: [UInt8] = Array("A22P".utf8)
    public static let supportedVersion = 1

    public let header: PlayHeader
    public let frameCount: Int
    public let entityCount: Int
    private let records: [Record]

    public init(contentsOf url: URL) throws {
        try self.init(data: Data(contentsOf: url))
    }

    public init(data input: Data) throws {
        let data = Data(input)  // re-based so offsets start at 0
        guard data.count >= 16 else { throw PlayFileError.truncated }
        guard Array(data.prefix(4)) == Self.magic else { throw PlayFileError.badMagic }
        let version = Int(data.readLE(UInt16.self, at: 4))
        guard version <= Self.supportedVersion else { throw PlayFileError.unsupportedVersion(version) }
        let headerLength = Int(data.readLE(UInt32.self, at: 8))
        guard data.count >= 12 + headerLength + 4 else { throw PlayFileError.truncated }

        let headerData = data.subdata(in: 12 ..< 12 + headerLength)
        let header: PlayHeader
        do {
            header = try JSONDecoder().decode(PlayHeader.self, from: headerData)
        } catch {
            throw PlayFileError.badHeader(String(describing: error))
        }

        let framesLength = Int(data.readLE(UInt32.self, at: 12 + headerLength))
        let framesStart = 16 + headerLength
        guard data.count >= framesStart + framesLength else { throw PlayFileError.truncated }
        var frames = data.subdata(in: framesStart ..< framesStart + framesLength)
        if header.frames.encoding == "deflate" {
            do {
                frames = try (frames as NSData).decompressed(using: .zlib) as Data
            } catch {
                throw PlayFileError.badFrames("could not inflate: \(error)")
            }
        }

        let entityCount = header.entities.count
        let frameCount = header.frames.count
        let size = header.frames.recordSize
        guard size >= 12 else { throw PlayFileError.badFrames("record size \(size)") }
        guard frames.count == frameCount * entityCount * size else {
            throw PlayFileError.badFrames("expected \(frameCount * entityCount * size) bytes, got \(frames.count)")
        }

        var records: [Record] = []
        records.reserveCapacity(frameCount * entityCount)
        frames.withUnsafeBytes { raw in
            for i in 0 ..< frameCount * entityCount {
                let o = i * size
                records.append(Record(
                    rawX: Int16(littleEndian: raw.loadUnaligned(fromByteOffset: o, as: Int16.self)),
                    rawY: Int16(littleEndian: raw.loadUnaligned(fromByteOffset: o + 2, as: Int16.self)),
                    rawSpeed: UInt16(littleEndian: raw.loadUnaligned(fromByteOffset: o + 4, as: UInt16.self)),
                    rawDirection: UInt16(littleEndian: raw.loadUnaligned(fromByteOffset: o + 6, as: UInt16.self)),
                    rawFacing: UInt16(littleEndian: raw.loadUnaligned(fromByteOffset: o + 8, as: UInt16.self)),
                    flags: UInt16(littleEndian: raw.loadUnaligned(fromByteOffset: o + 10, as: UInt16.self))
                ))
            }
        }
        self.header = header
        self.frameCount = frameCount
        self.entityCount = entityCount
        self.records = records
    }

    public func record(frame: Int, entity: Int) -> Record {
        let f = min(max(frame, 0), frameCount - 1)
        return records[f * entityCount + entity]
    }

    public var entities: [PlayEntity] { header.entities }
    public var frameRate: Double { Double(header.frames.rate) }
    /// Seconds from the first frame to the last.
    public var duration: Double { Double(max(frameCount - 1, 0)) / frameRate }

    public func time(ofFrame frame: Int) -> Double { Double(frame) / frameRate }
}

extension Data {
    func readLE<T: FixedWidthInteger>(_ type: T.Type, at offset: Int) -> T {
        withUnsafeBytes { raw in
            T(littleEndian: raw.loadUnaligned(fromByteOffset: offset, as: T.self))
        }
    }
}
