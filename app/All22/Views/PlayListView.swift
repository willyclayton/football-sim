import PlaybackCore
import SwiftUI

struct PlayListView: View {
    @Environment(PlayLibrary.self) private var library
    @State private var query = ""
    @State private var selected: PlaySummary?
    @State private var showLegend = false

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("All-22")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            showLegend = true
                        } label: {
                            Image(systemName: "checkmark.seal")
                        }
                        .accessibilityLabel("Where the data comes from")
                    }
                }
                .sheet(isPresented: $showLegend) { BadgeLegendView() }
        }
        .fullScreenCover(item: $selected) { summary in
            PlayViewerView(summary: summary)
                .environment(library)
        }
        .onAppear { Orientation.lock(.portrait) }
    }

    @ViewBuilder private var content: some View {
        switch library.state {
        case .idle:
            ProgressView()
        case .empty:
            EmptyLibraryView()
        case .failed(let message):
            ContentUnavailableView("Couldn't load plays", systemImage: "exclamationmark.triangle",
                                   description: Text(message))
        case .loaded:
            List {
                ForEach(library.sections(matching: query)) { section in
                    Section {
                        ForEach(section.plays) { play in
                            Button {
                                selected = play
                            } label: {
                                PlayRow(play: play)
                            }
                            .tint(.primary)
                        }
                    } header: {
                        Text(section.title)
                    } footer: {
                        if section.id == "review" {
                            Text("These failed a soft check. Compare each with the broadcast, then mark it "
                                 + "reviewed or dropped: make review PLAY=<id> VERDICT=reviewed")
                        }
                    }
                }
            }
            .listStyle(.insetGrouped)
            .searchable(text: $query, prompt: "Player, team, formation, result")
        }
    }
}

struct PlayRow: View {
    let play: PlaySummary

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Text("\(Format.quarterShort(play.quarter)) \(Format.clock(play.clock))")
                    .font(.caption.monospacedDigit().weight(.semibold))
                    .foregroundStyle(.secondary)
                if let dd = Format.downAndDistance(down: play.down, toGo: play.yardsToGo, goalToGo: false) {
                    Text(dd).font(.caption.weight(.semibold))
                }
                if let yl = play.yardline {
                    Text("at \(yl)").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if play.touchdown {
                    Text("TD")
                        .font(.caption2.weight(.heavy))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(.yellow, in: Capsule())
                        .foregroundStyle(.black)
                }
                if play.awaitingReview {
                    Image(systemName: "eye.trianglebadge.exclamationmark")
                        .foregroundStyle(.orange)
                        .accessibilityLabel("Awaiting video review")
                }
            }
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(play.offense ?? "")
                    .font(.subheadline.weight(.bold))
                Text(play.description ?? play.result ?? "")
                    .font(.subheadline)
                    .lineLimit(2)
            }
            let tags = [play.personnel, play.formation, play.receiverSet, play.defensivePackage]
                .compactMap { $0 }
            if !tags.isEmpty {
                Text(tags.joined(separator: " · "))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
    }
}

struct EmptyLibraryView: View {
    var body: some View {
        ContentUnavailableView {
            Label("No plays bundled", systemImage: "sportscourt")
        } description: {
            Text("The NFL tracking data never goes in git. On your Mac, run\n\n"
                 + "make bundle\n\n"
                 + "in the repo, then build the app again. It downloads the official sample game, "
                 + "checks every play and packs them into app/PlayData.")
        }
    }
}
