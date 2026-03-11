import SwiftUI

@main
struct ScreenMemoryMenuBarApp: App {
    var body: some Scene {
        MenuBarExtra("ScreenMemory", systemImage: "photo.on.rectangle.angled") {
            ContentView()
        }
        .menuBarExtraStyle(.window)
    }
}
