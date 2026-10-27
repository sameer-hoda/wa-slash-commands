// swift-tools-version: 5.10
// Package.swift — Mosaic macOS shell (BAMA-style Swift Package layout).
// Build with ./build.sh from the mac/ directory; do not invoke swiftc directly.
import PackageDescription

let package = Package(
    name: "Mosaic",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "Mosaic", targets: ["Mosaic"])
    ],
    targets: [
        .executableTarget(
            name: "Mosaic",
            path: "Sources/Mosaic"
        )
    ]
)
