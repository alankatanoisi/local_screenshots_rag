import SwiftUI

@main
struct ScreenMemoryMenuBarApp: App {
    var body: some Scene {
        MenuBarExtra("ScreenMemory", systemImage: "photo.badge.magnifyingglass") {
            ContentView()
        }
        .menuBarExtraStyle(.window)
    }
}
