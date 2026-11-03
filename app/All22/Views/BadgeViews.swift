import PlaybackCore
import SwiftUI

/// A small letter in the badge's color, e.g. "D" for Derived.
struct BadgeMark: View {
    let badge: Badge

    var body: some View {
        Text(badge.letter)
            .font(.system(size: 9, weight: .heavy, design: .rounded))
            .foregroundStyle(.white)
            .frame(width: 14, height: 14)
            .background(badge.color, in: RoundedRectangle(cornerRadius: 3))
            .accessibilityLabel(badge.title)
    }
}

/// "Derived" spelled out, for lists.
struct BadgePill: View {
    let badge: Badge

    var body: some View {
        Text(badge.title)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .foregroundStyle(badge.color)
            .background(badge.color.opacity(0.15), in: Capsule())
    }
}

struct BadgeLegendView: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(Badge.allCases.filter { $0 != .unknown }, id: \.self) { badge in
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            BadgeMark(badge: badge)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(badge.title).font(.headline)
                                Text(badge.meaning).font(.subheadline).foregroundStyle(.secondary)
                                Text(badge.verifiable ? "Verifiable against an official source"
                                                      : "Not verifiable: a judgment or an estimate")
                                    .font(.caption)
                                    .foregroundStyle(badge.verifiable ? .green : .orange)
                            }
                        }
                    }
                } footer: {
                    Text("Every on-screen fact carries one of these. Player and ball positions are tracked; "
                         + "ball height is derived from flight time; EPA and win probability are model estimates.")
                }
            }
            .navigationTitle("Where data comes from")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }
}
