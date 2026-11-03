import PlaybackCore
import SwiftUI

/// Teams, score, quarter, game clock (counting down from the snap) and down and distance.
struct Scorebug: View {
    let playback: Playback
    let time: Double

    var body: some View {
        let header = playback.header
        let sit = header.situation
        let score = sit.scoreBefore
        HStack(spacing: 0) {
            teamCell(header.game.away, score: score?.away, possession: sit.offense == "away")
            teamCell(header.game.home, score: score?.home, possession: sit.offense == "home")
            Divider().frame(height: 22).overlay(.white.opacity(0.3))
            Text(Format.quarterShort(sit.quarter))
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 8)
            if let clock = playback.gameClock(at: time) {
                Text(Playback.formatClock(clock))
                    .font(.caption.monospacedDigit().weight(.bold))
                    .padding(.trailing, 8)
            }
            if let dd = Format.downAndDistance(down: sit.down, toGo: sit.yardsToGo, goalToGo: sit.goalToGo ?? false) {
                Text(dd)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.black)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(.yellow)
            }
        }
        .foregroundStyle(.white)
        .background(.black.opacity(0.75), in: RoundedRectangle(cornerRadius: 6))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .accessibilityElement(children: .combine)
    }

    private func teamCell(_ team: Team, score: Int?, possession: Bool) -> some View {
        HStack(spacing: 4) {
            Text(team.abbr).font(.caption.weight(.heavy))
            Text(score.map { String($0) } ?? "-").font(.caption.monospacedDigit().weight(.bold))
            if possession {
                Image(systemName: "football.fill").font(.system(size: 8))
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .foregroundStyle(Color(hex: team.textColor))
        .background(Color(hex: team.primaryColor))
    }
}

/// Offense and defense callouts with their badges. Up at line set, they fade at the snap.
struct CalloutChips: View {
    let model: ViewerModel
    let time: Double

    var body: some View {
        let header = model.playback.header
        let callouts = header.callouts
        let opacity = chipOpacity
        VStack(alignment: .leading, spacing: 6) {
            if opacity > 0 {
                chipRow(title: "OFFENSE", items: callouts.offense).opacity(opacity)
                chipRow(title: "DEFENSE", items: callouts.defense).opacity(opacity)
            }
            if let snap = model.snapTime, time >= snap, !callouts.afterSnap.isEmpty {
                chipRow(title: "PLAY", items: callouts.afterSnap)
            }
            if header.synthetic == true {
                Text("SYNTHETIC TEST PLAY, NOT REAL DATA")
                    .font(.caption2.weight(.heavy))
                    .padding(4)
                    .background(.red, in: RoundedRectangle(cornerRadius: 4))
            }
        }
        .onTapGesture { model.showInfo = true }
    }

    private var chipOpacity: Double {
        if model.overlays.chipsAfterSnap { return 1 }
        guard let snap = model.snapTime else { return 1 }
        if time < snap { return 1 }
        return max(0, 1 - (time - snap) / 0.5)
    }

    private func chipRow(title: String, items: [Callout]) -> some View {
        HStack(spacing: 6) {
            Text(title)
                .font(.system(size: 9, weight: .heavy))
                .foregroundStyle(.white.opacity(0.7))
            ForEach(items) { c in
                HStack(spacing: 4) {
                    BadgeMark(badge: c.badge)
                    Text(c.label)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(c.missing ? .white.opacity(0.6) : .white)
                        .italic(c.missing)
                }
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(.black.opacity(0.7), in: Capsule())
    }
}

/// Name, position, speed now, top speed and distance run since the snap.
struct PlayerCard: View {
    let model: ViewerModel
    let entity: Int
    let time: Double

    var body: some View {
        let header = model.playback.header
        let e = header.entities[entity]
        let state = model.playback.state(ofEntity: entity, at: time)
        let stats = model.stats(forEntity: entity, through: time)
        let team = header.game.team(e.team)
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("#\(e.jersey.map { String($0) } ?? "?") \(e.name ?? "Unknown")")
                    .font(.headline)
                Spacer()
                Button {
                    model.selected = nil
                    if model.followed == entity {
                        model.followed = nil
                        model.camera = .play
                    }
                } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                }
            }
            Text([e.position, team?.abbr].compactMap { $0 }.joined(separator: " · "))
                .font(.subheadline)
                .foregroundStyle(.secondary)
            HStack(spacing: 14) {
                metric("Now", state.speed.map { String(format: "%.0f mph", Units.mph($0)) } ?? "-")
                metric("Top", String(format: "%.1f mph", stats.topSpeedMph))
                metric("Ran", String(format: "%.1f yds", stats.distance))
            }
            HStack(spacing: 4) {
                BadgeMark(badge: .tracked)
                Text(state.filled ? "Position filled across a short sensor gap" : "Positions and speeds from the sensors")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Button(model.followed == entity ? "Stop following" : "Follow") {
                if model.followed == entity {
                    model.followed = nil
                    model.camera = .play
                } else {
                    model.followed = entity
                    model.camera = .follow
                }
            }
            .font(.caption.weight(.semibold))
        }
        .padding(10)
        .frame(width: 260)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
    }

    private func metric(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title).font(.caption2).foregroundStyle(.secondary)
            Text(value).font(.subheadline.monospacedDigit().weight(.semibold))
        }
    }
}
