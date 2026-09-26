// swift-tools-version: 5.9
// Purpose: dependency-free SwiftUI shell target for IDE use and native builds.
// The packaged Python engine is assembled separately by scripts/build_macos.py.
import PackageDescription
let package = Package(name: "LumaRAW", platforms: [.macOS(.v14)], products: [.executable(name: "LumaRAW", targets: ["LumaRAW"])], targets: [.executableTarget(name: "LumaRAW", path: "native")])
