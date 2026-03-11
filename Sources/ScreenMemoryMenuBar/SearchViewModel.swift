import AppKit
import Foundation

@MainActor
final class SearchViewModel: ObservableObject {
    // This object owns the UI state for the menu bar app.
    @Published var queryText = ""
    @Published var selectedMode: QueryMode = .ocrOnly
    @Published var response: SearchResponseDTO?
    @Published var status: StatusDTO?
    @Published var errorMessage: String?
    @Published var isSearching = false
    @Published var selectedResult: SearchResultDTO?

    private let runner = CLIRunner()

    func refreshStatus() {
        Task {
            do {
                status = try runner.fetchStatus()
                errorMessage = nil
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func runSearch() {
        let trimmed = queryText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        isSearching = true
        errorMessage = nil

        Task {
            do {
                let newResponse = try runner.search(query: trimmed, mode: selectedMode)
                response = newResponse
                selectedResult = newResponse.results.first
                isSearching = false
            } catch {
                response = nil
                selectedResult = nil
                errorMessage = error.localizedDescription
                isSearching = false
            }
        }
    }

    func openSelectedFile() {
        guard let path = selectedResult?.file_path else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    func revealSelectedFile() {
        guard let path = selectedResult?.file_path else { return }
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
    }

    func copySelectedPath() {
        guard let path = selectedResult?.file_path else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(path, forType: .string)
    }

    func clearSearch() {
        // Clearing the UI state makes it obvious that the next query is a fresh search.
        queryText = ""
        response = nil
        selectedResult = nil
        errorMessage = nil
        isSearching = false
    }

    func quitApp() {
        NSApplication.shared.terminate(nil)
    }

    func closePanel() {
        // The menu bar extra behaves like a normal window behind the scenes.
        // Closing that window hides the panel without quitting the whole app.
        NSApp.keyWindow?.close()
    }

    func selectCitation(_ citation: AnswerCitationDTO) {
        guard citation.result_index >= 0, let response, citation.result_index < response.results.count else {
            return
        }
        selectedResult = response.results[citation.result_index]
    }
}
