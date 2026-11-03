// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "PlaybackCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "PlaybackCore", targets: ["PlaybackCore"]),
    ],
    targets: [
        .target(
            name: "PlaybackCore",
            linkerSettings: [.linkedLibrary("sqlite3")]
        ),
        .testTarget(
            name: "PlaybackCoreTests",
            dependencies: ["PlaybackCore"],
            resources: [.copy("Fixtures")]
        ),
    ]
)
