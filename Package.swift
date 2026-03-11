// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "ScreenMemoryMenuBar",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .executable(
            name: "ScreenMemoryMenuBar",
            targets: ["ScreenMemoryMenuBar"]
        ),
    ],
    targets: [
        .executableTarget(
            name: "ScreenMemoryMenuBar",
            path: "Sources/ScreenMemoryMenuBar"
        ),
    ]
)
