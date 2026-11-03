import CoreGraphics
import PlaybackCore

/// Maps field yards to view points. Looking from the home sideline: the offense
/// attacks to the right (+x), and its left (+y) is the far side, at the top.
struct FieldTransform: Equatable {
    let rect: CGRect  // visible field area, in yards
    let size: CGSize  // view size, in points
    let scale: CGFloat  // points per yard
    let origin: CGPoint

    init(rect: CGRect, size: CGSize) {
        let fitted = FieldTransform.fit(rect, to: size)
        self.rect = fitted
        self.size = size
        let s = min(size.width / max(fitted.width, 1), size.height / max(fitted.height, 1))
        scale = s
        origin = CGPoint(x: (size.width - fitted.width * s) / 2, y: (size.height - fitted.height * s) / 2)
    }

    func point(_ x: Double, _ y: Double) -> CGPoint {
        CGPoint(x: origin.x + (x - rect.minX) * scale, y: origin.y + (rect.maxY - y) * scale)
    }

    func field(at p: CGPoint) -> (x: Double, y: Double) {
        (Double((p.x - origin.x) / scale + rect.minX), Double(rect.maxY - (p.y - origin.y) / scale))
    }

    func length(_ yards: Double) -> CGFloat { yards * scale }

    /// Grow `rect` to the view's aspect ratio so the field fills the screen.
    static func fit(_ rect: CGRect, to size: CGSize) -> CGRect {
        guard size.width > 0, size.height > 0, rect.width > 0, rect.height > 0 else { return rect }
        let aspect = size.width / size.height
        var r = rect
        if r.width / r.height < aspect {
            let w = r.height * aspect
            r = r.insetBy(dx: -(w - r.width) / 2, dy: 0)
        } else {
            let h = r.width / aspect
            r = r.insetBy(dx: 0, dy: -(h - r.height) / 2)
        }
        return r
    }
}

/// The visible field area for each camera mode, in yards.
enum CameraFraming {
    static let fullField = CGRect(x: -2, y: -2, width: Field.length + 4, height: Field.width + 4)

    static func rect(mode: CameraMode, model: ViewerModel, ballX: Double, ballY: Double,
                     followedX: Double?, followedY: Double?) -> CGRect {
        switch mode {
        case .fullField:
            return fullField
        case .play:
            return model.playExtent
        case .follow:
            let cx = followedX ?? ballX
            let cy = followedY ?? ballY
            return CGRect(x: cx - 20, y: cy - 12, width: 40, height: 24)
        case .free:
            return model.freeRect ?? model.playExtent
        }
    }
}
