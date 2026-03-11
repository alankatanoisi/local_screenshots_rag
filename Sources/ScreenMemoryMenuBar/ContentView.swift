import SwiftUI

struct CitationListView: View {
    let citations: [AnswerCitationDTO]
    let onSelect: (AnswerCitationDTO) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Citations")
                .font(.caption)
                .fontWeight(.semibold)

            ForEach(citations) { citation in
                Button {
                    onSelect(citation)
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("[\(citation.footnote)] \(citation.captured_at_local)")
                            .font(.caption)
                            .fontWeight(.medium)
                            .lineLimit(1)

                        Text(citation.snippet)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 2)
                }
                .buttonStyle(.plain)
            }
        }
    }
}

struct CompactResultRow: View {
    let result: SearchResultDTO
    let isSelected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(result.captured_at_local)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                Spacer(minLength: 0)

                Text(String(format: "%.2f", result.score))
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            Text(result.snippet)
                .font(.caption)
                .lineLimit(2)

            Text(result.file_path)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(isSelected ? Color.accentColor.opacity(0.14) : Color.secondary.opacity(0.06))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(isSelected ? Color.accentColor.opacity(0.8) : Color.clear, lineWidth: 1)
        )
    }
}

struct CompactAnswerCard: View {
    let answer: String
    let citations: [AnswerCitationDTO]
    let onSelectCitation: (AnswerCitationDTO) -> Void

    @State private var isExpanded = false
    @State private var showCitations = false

    private var citationSummary: String {
        if citations.isEmpty {
            return "No citations"
        }
        return citations.prefix(4).map { "[\($0.footnote)]" }.joined(separator: " ")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Gemini Answer")
                    .font(.caption)
                    .fontWeight(.semibold)

                Spacer()

                if !citations.isEmpty {
                    Text(citationSummary)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Button(isExpanded ? "Collapse" : "Expand") {
                    isExpanded.toggle()
                }
                .font(.caption)
            }

            Text(answer)
                .font(.caption)
                .lineLimit(isExpanded ? nil : 4)
                .fixedSize(horizontal: false, vertical: true)

            if !citations.isEmpty {
                Button(showCitations ? "Hide Citations" : "Show Citations") {
                    showCitations.toggle()
                }
                .font(.caption)

                if showCitations {
                    CitationListView(
                        citations: citations,
                        onSelect: onSelectCitation
                    )
                }
            }
        }
        .padding(10)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

struct ContentView: View {
    @StateObject private var viewModel = SearchViewModel()

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            header
            searchBar

            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage)
                    .font(.caption2)
                    .foregroundStyle(.red)
                    .lineLimit(6)
                    .textSelection(.enabled)
            }

            if viewModel.isSearching {
                ProgressView("Searching...")
                    .font(.caption)
            }

            resultsSection

            if let response = viewModel.response, let answer = response.answer, !answer.isEmpty {
                CompactAnswerCard(
                    answer: answer,
                    citations: response.citations,
                    onSelectCitation: { citation in
                        viewModel.selectCitation(citation)
                    }
                )
            }

            Divider()
            footer
        }
        .padding(12)
        .frame(width: 760, height: 540)
        .onAppear {
            viewModel.refreshStatus()
        }
    }

    private var header: some View {
        HStack {
            Text("ScreenMemory RAG")
                .font(.headline)

            Spacer()

            Button("Close Panel") {
                viewModel.closePanel()
            }
            .font(.caption)
        }
    }

    private var searchBar: some View {
        HStack(spacing: 8) {
            TextField("Search your screenshot history", text: $viewModel.queryText)
                .textFieldStyle(.roundedBorder)
                .onSubmit {
                    viewModel.runSearch()
                }

            Picker("Mode", selection: $viewModel.selectedMode) {
                ForEach(QueryMode.allCases) { mode in
                    Text(mode.label).tag(mode)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 200)

            Button("Search") {
                viewModel.runSearch()
            }
            .keyboardShortcut(.defaultAction)

            Button("Clear") {
                viewModel.clearSearch()
            }
        }
    }

    private var resultsSection: some View {
        Group {
            if let results = viewModel.response?.results, !results.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    ResultThumbnailStrip(
                        results: results,
                        selected: viewModel.selectedResult,
                        onSelect: { result in
                            viewModel.selectedResult = result
                        }
                    )

                    HStack(alignment: .top, spacing: 10) {
                        previewPane
                        resultList(results: results)
                    }
                }
            } else {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.secondary.opacity(0.06))
                    .overlay(alignment: .leading) {
                        Text("Search results and thumbnail quick-look previews will appear here.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 12)
                    }
                    .frame(height: 160)
            }
        }
    }

    private var previewPane: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let selected = viewModel.selectedResult {
                ThumbnailImageView(
                    filePath: selected.thumbnail_path ?? selected.file_path,
                    maxHeight: 170
                )
                .frame(width: 250, height: 170)

                HStack(spacing: 8) {
                    Button("Open") {
                        viewModel.openSelectedFile()
                    }

                    Button("Reveal") {
                        viewModel.revealSelectedFile()
                    }

                    Button("Copy Path") {
                        viewModel.copySelectedPath()
                    }
                }
                .font(.caption)
            } else {
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.secondary.opacity(0.06))
                    .frame(width: 250, height: 170)
                    .overlay {
                        Text("Select a result")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
            }
        }
        .frame(width: 250, alignment: .topLeading)
    }

    private func resultList(results: [SearchResultDTO]) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 8) {
                ForEach(results) { result in
                    Button {
                        viewModel.selectedResult = result
                    } label: {
                        CompactResultRow(
                            result: result,
                            isSelected: viewModel.selectedResult?.id == result.id
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.trailing, 4)
        }
        .frame(maxWidth: .infinity, minHeight: 230, maxHeight: 230)
    }

    private var footer: some View {
        HStack {
            VStack(alignment: .leading, spacing: 3) {
                Text("Indexed screenshots: \(viewModel.status?.screenshot_count ?? 0)")
                    .font(.caption)
                Text("Indexed chunks: \(viewModel.status?.chunk_count ?? 0)")
                    .font(.caption)
                Text("Last scan: \(viewModel.status?.last_successful_scan_at ?? "Not yet run")")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            HStack(spacing: 8) {
                Button("Clear Search") {
                    viewModel.clearSearch()
                }

                Button("Refresh Status") {
                    viewModel.refreshStatus()
                }

                Button("Quit App") {
                    viewModel.quitApp()
                }
            }
            .font(.caption)
        }
    }
}
