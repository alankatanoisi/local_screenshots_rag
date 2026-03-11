import AppKit
import SwiftUI

struct ThumbnailImageView: View {
    let filePath: String?
    let maxHeight: CGFloat

    var body: some View {
        Group {
            if let filePath, let image = NSImage(contentsOfFile: filePath) {
                Image(nsImage: image)
                    .resizable()
                    .scaledToFit()
            } else {
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.gray.opacity(0.15))
                    .overlay(
                        Text("No Preview")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    )
            }
        }
        .frame(maxHeight: maxHeight)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

struct ResultThumbnailStrip: View {
    let results: [SearchResultDTO]
    let selected: SearchResultDTO?
    let onSelect: (SearchResultDTO) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(results.prefix(6), id: \.id) { result in
                    Button {
                        onSelect(result)
                    } label: {
                        ThumbnailImageView(filePath: result.thumbnail_path, maxHeight: 70)
                            .frame(width: 120, height: 70)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(
                                        selected?.id == result.id ? Color.accentColor : Color.clear,
                                        lineWidth: 2
                                    )
                            )
                    }
                    .buttonStyle(.plain)
                    .help(result.file_path)
                }
            }
        }
    }
}
