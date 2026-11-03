import PlaybackCore
import SwiftUI

/// The official description, every callout with its badge, and the checks the play passed.
struct PlayInfoView: View {
    let header: PlayHeader
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    if let d = header.outcome.description {
                        Text(d)
                    }
                    row("Result", header.outcome.result, badge: .official)
                    if let epa = header.outcome.epa {
                        row("EPA", Format.signed(epa), badge: .model)
                    }
                    if let wpa = header.outcome.wpa {
                        row("Win probability added", Format.signed(wpa * 100, digits: 1) + " pts", badge: .model)
                    }
                    if let mph = header.stats.topSpeedMph, let who = header.stats.topSpeedName {
                        row("Top speed", String(format: "%.1f mph", mph) + ", " + who, badge: .tracked)
                    }
                    if let air = header.stats.airYards {
                        row("Ball in the air", String(format: "%.1f yds", air), badge: .tracked)
                    }
                } header: {
                    Text("\(header.game.away.abbr) at \(header.game.home.abbr) · \(header.game.date ?? "") · Week \(header.game.week)")
                }

                Section("Callouts") {
                    ForEach(header.callouts.offense + header.callouts.defense + header.callouts.afterSnap) { c in
                        VStack(alignment: .leading, spacing: 3) {
                            HStack {
                                Text(c.label).font(.body.weight(.semibold))
                                Spacer()
                                BadgePill(badge: c.badge)
                            }
                            if let detail = c.detail {
                                Text(detail).font(.caption).foregroundStyle(.secondary)
                            }
                            if let source = c.source {
                                Text(source).font(.caption2).foregroundStyle(.tertiary)
                            }
                        }
                    }
                }

                Section {
                    ForEach(header.checks.hard + header.checks.soft) { check in
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Image(systemName: icon(for: check.result))
                                .foregroundStyle(color(for: check.result))
                            VStack(alignment: .leading, spacing: 2) {
                                Text(check.name).font(.subheadline.weight(.semibold))
                                Text(check.detail).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                    ForEach(header.checks.notes, id: \.self) { note in
                        Label(note, systemImage: "note.text").font(.caption)
                    }
                } header: {
                    Text("Checks")
                } footer: {
                    Text("Hard checks drop a play when they fail; soft checks hold it for video review.")
                }

                Section("Video review") {
                    switch header.review.status {
                    case "reviewed":
                        Label("Reviewed \(header.review.date ?? "")", systemImage: "checkmark.seal.fill")
                            .foregroundStyle(.green)
                    case "dropped":
                        Label("Dropped at review", systemImage: "xmark.seal").foregroundStyle(.red)
                    default:
                        if header.checks.status == "flagged" {
                            Label("Awaiting video review", systemImage: "eye.trianglebadge.exclamationmark")
                                .foregroundStyle(.orange)
                        } else {
                            Label("Passed every check; no review needed", systemImage: "checkmark.circle")
                        }
                    }
                    if let note = header.review.note {
                        Text(note).font(.caption)
                    }
                }

                Section("Source") {
                    row("Edition", header.edition.name ?? header.edition.id, badge: nil)
                    row("Play", header.id, badge: nil)
                    if let flipped = header.provenance?.flipped {
                        row("Flipped to attack right", flipped ? "Yes" : "No", badge: nil)
                    }
                    if let version = header.provenance?.pipelineVersion {
                        row("Pipeline", version, badge: nil)
                    }
                }
            }
            .navigationTitle("Play info")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }

    private func row(_ title: String, _ value: String?, badge: Badge?) -> some View {
        HStack {
            Text(title).foregroundStyle(.secondary)
            Spacer()
            Text(value ?? "-").multilineTextAlignment(.trailing)
            if let badge { BadgeMark(badge: badge) }
        }
        .font(.subheadline)
    }

    private func icon(for result: String) -> String {
        switch result {
        case "pass": return "checkmark.circle.fill"
        case "fixed": return "wrench.and.screwdriver.fill"
        case "fail": return "exclamationmark.triangle.fill"
        default: return "minus.circle"
        }
    }

    private func color(for result: String) -> Color {
        switch result {
        case "pass": return .green
        case "fixed": return .blue
        case "fail": return .orange
        default: return .secondary
        }
    }
}
