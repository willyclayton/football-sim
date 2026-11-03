import PlaybackCore
import SwiftUI

/// Full-screen, landscape replay of one play.
struct PlayViewerView: View {
    let summary: PlaySummary
    @Environment(PlayLibrary.self) private var library
    @Environment(\.dismiss) private var dismiss
    @State private var model: ViewerModel?
    @State private var loadError: String?

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if let model {
                ViewerScreen(model: model, close: { dismiss() })
            } else if let loadError {
                VStack(spacing: 16) {
                    ContentUnavailableView("Couldn't open this play", systemImage: "exclamationmark.triangle",
                                           description: Text(loadError))
                    Button("Close") { dismiss() }
                }
            } else {
                ProgressView()
            }
        }
        .task {
            do {
                let file = try library.playFile(for: summary)
                model = ViewerModel(playback: Playback(file: file))
            } catch {
                loadError = String(describing: error)
            }
        }
        .onAppear { Orientation.lock(.landscape) }
        .onDisappear { Orientation.lock(.portrait) }
        .statusBarHidden()
        .persistentSystemOverlays(.hidden)
        .preferredColorScheme(.dark)
    }
}

struct ViewerScreen: View {
    @Bindable var model: ViewerModel
    let close: () -> Void
    @State private var gestureStart: CGRect?

    var body: some View {
        TimelineView(.animation(minimumInterval: nil, paused: !model.isPlaying)) { timeline in
            let t = model.time(at: timeline.date)
            GeometryReader { geo in
                let snapshot = makeSnapshot(time: t, size: geo.size)
                ZStack {
                    background(for: snapshot.transform).equatable()
                    PlayersLayer(snapshot: snapshot)
                }
                .contentShape(Rectangle())
                .onTapGesture(count: 2) { location in
                    if let hit = hitTest(location, in: snapshot) {
                        model.selected = hit
                        model.followed = hit
                        model.camera = .follow
                    }
                }
                .onTapGesture { location in
                    model.selected = hitTest(location, in: snapshot)
                }
                .gesture(panGesture(snapshot.transform))
                .simultaneousGesture(zoomGesture(snapshot.transform))
            }
            .ignoresSafeArea()
            .overlay(alignment: .top) {
                HStack(alignment: .top) {
                    CalloutChips(model: model, time: t)
                    Spacer(minLength: 12)
                    Scorebug(playback: model.playback, time: t)
                }
                .padding(.horizontal, 12)
                .padding(.top, 8)
            }
            .overlay(alignment: .bottomLeading) {
                if let selected = model.selected {
                    PlayerCard(model: model, entity: selected, time: t)
                        .padding(.leading, 12)
                        .padding(.bottom, 64)
                }
            }
            .overlay(alignment: .bottom) {
                ControlsBar(model: model, time: t, close: close)
                    .padding(.horizontal, 8)
                    .padding(.bottom, 4)
            }
            .onChange(of: timeline.date) { _, date in
                model.tick(at: date)
            }
        }
        .sensoryFeedback(.impact(weight: .light), trigger: model.hapticTick)
        .sheet(isPresented: $model.showInfo) {
            PlayInfoView(header: model.playback.header)
        }
    }

    // MARK: Drawing inputs

    private func background(for transform: FieldTransform) -> FieldBackground {
        let header = model.playback.header
        let offenseIsHome = header.situation.offense == "home"
        let offense = offenseIsHome ? header.game.home : header.game.away
        let defense = offenseIsHome ? header.game.away : header.game.home
        return FieldBackground(transform: transform, leftEndZone: offense, rightEndZone: defense,
                               losX: header.situation.losX, lineToGainX: header.situation.lineToGainX,
                               showLines: model.overlays.lines)
    }

    private func makeSnapshot(time t: Double, size: CGSize) -> FrameSnapshot {
        let pb = model.playback
        let header = pb.header
        let ball = pb.ballState(at: t)
        let followedState = model.followed.map { pb.state(ofEntity: $0, at: t) }
        let rect = CameraFraming.rect(mode: model.camera, model: model, ballX: ball.x, ballY: ball.y,
                                      followedX: followedState?.x, followedY: followedState?.y)
        let transform = FieldTransform(rect: rect, size: size)
        let home = TeamPaint(team: header.game.home, home: true)
        let away = TeamPaint(team: header.game.away, home: false)
        let frameNow = Int(pb.frame(at: t))

        var players: [FrameSnapshot.Player] = []
        var trails: [FrameSnapshot.Trail] = []
        let snap = header.keyFrames.snap ?? header.keyFrames.kick
        for (i, e) in header.entities.enumerated() where !e.isBall {
            let st = pb.state(ofEntity: i, at: t)
            guard st.present else { continue }
            let paint = e.team == "home" ? home : away
            let moving = (st.speed ?? 0) > 1.0
            let heading = st.facing ?? (moving ? st.direction : nil)
            players.append(FrameSnapshot.Player(
                index: i, x: st.x, y: st.y, speed: st.speed, heading: heading, filled: st.filled,
                fill: paint.fill, ring: paint.ring, text: paint.text,
                label: e.name.map(Self.lastName) ?? "", jerseyText: e.jersey.map { String($0) } ?? ""))

            if let snap, frameNow > snap, e.isOffense, ["RB", "WR", "TE"].contains(e.group ?? "") {
                var points: [CGPoint] = []
                for f in snap ... frameNow {
                    let r = pb.file.record(frame: f, entity: i)
                    if r.hasPosition { points.append(CGPoint(x: r.x, y: r.y)) }
                }
                points.append(CGPoint(x: st.x, y: st.y))
                trails.append(FrameSnapshot.Trail(points: points, color: e.team == "home" ? home.fill : away.ring))
            }
        }

        // The throw's tracked path, once the ball is in the air.
        var ballPath: [CGPoint] = []
        if let flight = header.ball.segments.last(where: { $0.mode == .flight && $0.from <= frameNow && $0.to - $0.from >= 3 }) {
            for f in flight.from ... min(flight.to, frameNow) {
                let r = pb.file.record(frame: f, entity: 0)
                if r.hasPosition { ballPath.append(CGPoint(x: r.x, y: r.y)) }
            }
        }

        return FrameSnapshot(transform: transform, players: players, ball: ball, trails: trails,
                             ballPath: ballPath, overlays: model.overlays, selected: model.selected,
                             separation: separation(at: t))
    }

    /// Receiver to nearest defender at the catch, shown for two seconds after it.
    private func separation(at t: Double) -> FrameSnapshot.Separation? {
        let pb = model.playback
        let header = pb.header
        guard let catchFrame = header.keyFrames.catchFrame else { return nil }
        let catchTime = pb.time(ofFrame: catchFrame)
        guard t >= catchTime, t <= catchTime + 2 else { return nil }
        guard let receiver = header.ball.segments.first(where: { $0.mode == .held && $0.from >= catchFrame - 1 })?.holder
            ?? header.carrier else { return nil }
        let r = pb.file.record(frame: catchFrame, entity: receiver)
        guard r.hasPosition else { return nil }
        let receiverSide = header.entities[receiver].side
        var best: (Int, Double)?
        for (i, e) in header.entities.enumerated() where !e.isBall && e.side != receiverSide {
            let d = pb.file.record(frame: catchFrame, entity: i)
            guard d.hasPosition else { continue }
            let dist = hypot(d.x - r.x, d.y - r.y)
            if best == nil || dist < best!.1 { best = (i, dist) }
        }
        guard let best else { return nil }
        let d = pb.file.record(frame: catchFrame, entity: best.0)
        return FrameSnapshot.Separation(from: CGPoint(x: r.x, y: r.y), to: CGPoint(x: d.x, y: d.y), yards: best.1)
    }

    private func hitTest(_ location: CGPoint, in snapshot: FrameSnapshot) -> Int? {
        let p = snapshot.transform.field(at: location)
        let hit = snapshot.players
            .map { ($0.index, hypot($0.x - p.x, $0.y - p.y)) }
            .min { $0.1 < $1.1 }
        guard let hit, hit.1 < 2.5 else { return nil }
        return hit.0
    }

    static func lastName(_ name: String) -> String {
        name.split(separator: " ").last.map(String.init) ?? name
    }

    // MARK: Free camera

    private func panGesture(_ transform: FieldTransform) -> some Gesture {
        DragGesture(minimumDistance: 12)
            .onChanged { value in
                let start = gestureStart ?? transform.rect
                if gestureStart == nil {
                    gestureStart = start
                    model.camera = .free
                }
                let dx = value.translation.width / transform.scale
                let dy = value.translation.height / transform.scale
                model.freeRect = start.offsetBy(dx: -dx, dy: dy)
            }
            .onEnded { _ in gestureStart = nil }
    }

    private func zoomGesture(_ transform: FieldTransform) -> some Gesture {
        MagnifyGesture()
            .onChanged { value in
                let start = gestureStart ?? transform.rect
                if gestureStart == nil {
                    gestureStart = start
                    model.camera = .free
                }
                let k = 1 / max(value.magnification, 0.1)
                let w = min(max(start.width * k, 12), 140)
                let h = start.height * (w / start.width)
                model.freeRect = CGRect(x: start.midX - w / 2, y: start.midY - h / 2, width: w, height: h)
            }
            .onEnded { _ in gestureStart = nil }
    }
}
