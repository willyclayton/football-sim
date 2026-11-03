import PlaybackCore
import SwiftUI

/// Close, frame step, play/pause, scrubber with event markers, speed, loop,
/// camera, overlays and play info.
struct ControlsBar: View {
    @Bindable var model: ViewerModel
    let time: Double
    let close: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: close) { Image(systemName: "xmark") }
                .accessibilityLabel("Close")
            Button { model.step(frames: -1) } label: { Image(systemName: "backward.frame.fill") }
                .accessibilityLabel("Back one frame")
            Button { model.togglePlay() } label: {
                Image(systemName: model.isPlaying ? "pause.fill" : "play.fill")
                    .font(.title3)
                    .frame(width: 28)
            }
            .accessibilityLabel(model.isPlaying ? "Pause" : "Play")
            Button { model.step(frames: 1) } label: { Image(systemName: "forward.frame.fill") }
                .accessibilityLabel("Forward one frame")

            ScrubberView(model: model, time: time)

            Text(timeLabel)
                .font(.caption.monospacedDigit())
                .frame(width: 44, alignment: .trailing)

            Menu {
                ForEach(ViewerModel.rates, id: \.self) { r in
                    Button {
                        model.setRate(r)
                    } label: {
                        if r == model.rate { Label(rateText(r), systemImage: "checkmark") } else { Text(rateText(r)) }
                    }
                }
            } label: {
                Text(rateText(model.rate))
                    .font(.caption.weight(.bold).monospacedDigit())
                    .frame(width: 40)
            }

            Button { model.loop.toggle() } label: {
                Image(systemName: "repeat").foregroundStyle(model.loop ? Color.accentColor : .white)
            }
            .accessibilityLabel(model.loop ? "Loop on" : "Loop off")

            Menu {
                Picker("Camera", selection: $model.camera) {
                    ForEach(CameraMode.allCases) { mode in
                        Label(mode.rawValue, systemImage: mode.symbol).tag(mode)
                    }
                }
            } label: {
                Image(systemName: model.camera.symbol)
            }
            .accessibilityLabel("Camera")

            Menu {
                Toggle("Route trails", isOn: $model.overlays.routes)
                Toggle("Ball path", isOn: $model.overlays.ballPath)
                Toggle("Line of scrimmage and line to gain", isOn: $model.overlays.lines)
                Toggle("Names", isOn: $model.overlays.names)
                Toggle("Speeds (mph)", isOn: $model.overlays.speeds)
                Toggle("Separation at the catch", isOn: $model.overlays.separation)
                Toggle("Keep callouts after the snap", isOn: $model.overlays.chipsAfterSnap)
            } label: {
                Image(systemName: "square.3.layers.3d")
            }
            .accessibilityLabel("Overlays")

            Button { model.showInfo = true } label: { Image(systemName: "info.circle") }
                .accessibilityLabel("Play info")
        }
        .foregroundStyle(.white)
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.black.opacity(0.65), in: RoundedRectangle(cornerRadius: 12))
    }

    private var timeLabel: String {
        // Time relative to the snap reads like a stopwatch on the play.
        guard let snap = model.snapTime else { return String(format: "%.1fs", time) }
        let d = time - snap
        return String(format: d < 0 ? "%.1fs" : "+%.1fs", d)
    }

    private func rateText(_ r: Double) -> String {
        r == r.rounded() ? "\(Int(r))×" : String(format: "%g×", r)
    }
}

/// Timeline with event markers (snap, throw, catch, contact, tackle...). Drag to scrub.
struct ScrubberView: View {
    let model: ViewerModel
    let time: Double
    @State private var wasPlaying = false
    @State private var dragging = false

    private struct Marker: Identifiable {
        let id: Int
        let fraction: Double
        let label: String
        let showLabel: Bool
    }

    var body: some View {
        GeometryReader { geo in
            let width = geo.size.width
            let duration = max(model.duration, 0.1)
            let progress = min(max(time / duration, 0), 1)
            let marks = markers(width: width, duration: duration)
            ZStack(alignment: .topLeading) {
                Capsule()
                    .fill(.white.opacity(0.25))
                    .frame(width: width, height: 4)
                    .offset(y: 22)
                Capsule()
                    .fill(.white)
                    .frame(width: width * progress, height: 4)
                    .offset(y: 22)
                ForEach(marks) { m in
                    VStack(spacing: 2) {
                        Text(m.showLabel ? m.label : " ")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(.white.opacity(0.85))
                            .fixedSize()
                        Rectangle()
                            .fill(.yellow)
                            .frame(width: 2, height: 10)
                    }
                    .position(x: width * m.fraction, y: 13)
                }
                Circle()
                    .fill(.white)
                    .frame(width: 14, height: 14)
                    .position(x: width * progress, y: 24)
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        if !dragging {
                            dragging = true
                            wasPlaying = model.isPlaying
                            if wasPlaying { model.pause() }
                        }
                        model.seek(to: min(max(value.location.x / width, 0), 1) * duration)
                    }
                    .onEnded { _ in
                        dragging = false
                        if wasPlaying { model.play() }
                    }
            )
        }
        .frame(height: 32)
    }

    private func markers(width: CGFloat, duration: Double) -> [Marker] {
        let events = model.playback.header.events.filter(\.marker)
        var out: [Marker] = []
        var lastLabelX = -CGFloat.infinity
        for (i, e) in events.enumerated() {
            let fraction = model.playback.time(ofFrame: e.frame) / duration
            let x = width * fraction
            let show = x - lastLabelX > 44
            if show { lastLabelX = x }
            out.append(Marker(id: i, fraction: fraction, label: e.label, showLabel: show))
        }
        return out
    }
}
