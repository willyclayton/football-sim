import SwiftUI

@main
struct All22App: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var library = PlayLibrary()

    var body: some Scene {
        WindowGroup {
            PlayListView()
                .environment(library)
                .task { library.loadIfNeeded() }
        }
    }
}

/// Browse in portrait, watch in landscape: the delegate reports whichever
/// orientations the current screen allows.
final class AppDelegate: NSObject, UIApplicationDelegate {
    @MainActor static var orientationLock: UIInterfaceOrientationMask = .portrait

    func application(_ application: UIApplication,
                     supportedInterfaceOrientationsFor window: UIWindow?) -> UIInterfaceOrientationMask {
        Self.orientationLock
    }
}

@MainActor
enum Orientation {
    static func lock(_ mask: UIInterfaceOrientationMask) {
        AppDelegate.orientationLock = mask
        guard let scene = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene }).first else { return }
        scene.requestGeometryUpdate(.iOS(interfaceOrientations: mask)) { _ in }
        for window in scene.windows {
            window.rootViewController?.setNeedsUpdateOfSupportedInterfaceOrientations()
        }
    }
}
