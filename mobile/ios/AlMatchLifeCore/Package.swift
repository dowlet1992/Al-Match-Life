// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AlMatchLifeCore",
    platforms: [.iOS(.v16), .macOS(.v13)],
    products: [.library(name: "AlMatchLifeCore", targets: ["AlMatchLifeCore"])],
    targets: [
        .target(name: "AlMatchLifeCore"),
        .testTarget(name: "AlMatchLifeCoreTests", dependencies: ["AlMatchLifeCore"]),
    ]
)
