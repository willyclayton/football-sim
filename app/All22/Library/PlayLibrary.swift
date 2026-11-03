import Foundation
import Observation
import PlaybackCore

/// The plays bundled into the app by `make bundle` (folder PlayData).
@MainActor
@Observable
final class PlayLibrary {
    enum LoadState: Equatable {
        case idle
        case loaded
        case empty
        case failed(String)
    }

    struct PlaySection: Identifiable {
        let id: String
        let title: String
        let plays: [PlaySummary]
    }

    private(set) var plays: [PlaySummary] = []
    private(set) var state: LoadState = .idle

    private let root: URL? = Bundle.main.url(forResource: "PlayData", withExtension: nil)

    func loadIfNeeded() {
        guard state == .idle else { return }
        guard let root else {
            state = .empty
            return
        }
        let catalog = root.appending(path: "catalog.sqlite")
        guard FileManager.default.fileExists(atPath: catalog.path) else {
            state = .empty
            return
        }
        do {
            plays = try Catalog.load(from: catalog)
            state = plays.isEmpty ? .empty : .loaded
        } catch {
            state = .failed(String(describing: error))
        }
    }

    func playFile(for summary: PlaySummary) throws -> PlayFile {
        guard let root else { throw PlayFileError.truncated }
        return try PlayFile(contentsOf: root.appending(path: summary.file))
    }

    /// Plays grouped by game and quarter; plays awaiting video review go last, apart.
    func sections(matching query: String) -> [PlaySection] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        let matches = q.isEmpty ? plays : plays.filter { $0.searchText.contains(q) }
        var out: [PlaySection] = []
        var current: [PlaySummary] = []
        var currentKey = ""
        var currentTitle = ""
        for play in matches where !play.awaitingReview {
            let key = "\(play.gameId)-\(play.quarter ?? 0)"
            if key != currentKey, !current.isEmpty {
                out.append(PlaySection(id: currentKey, title: currentTitle, plays: current))
                current = []
            }
            currentKey = key
            currentTitle = "\(play.away) at \(play.home) · \(Format.quarterName(play.quarter))"
            current.append(play)
        }
        if !current.isEmpty {
            out.append(PlaySection(id: currentKey, title: currentTitle, plays: current))
        }
        let flagged = matches.filter(\.awaitingReview)
        if !flagged.isEmpty {
            out.append(PlaySection(id: "review", title: "Awaiting video review", plays: flagged))
        }
        return out
    }
}

extension PlaySummary {
    var searchText: String {
        [description, offense, defense, formation, personnel, receiverSet, defensivePackage,
         coverage, result, playType, topSpeedName]
            .compactMap { $0 }
            .joined(separator: " ")
            .lowercased()
    }
}
