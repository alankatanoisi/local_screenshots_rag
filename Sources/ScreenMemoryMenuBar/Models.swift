import Foundation

// Swift uses `//` comments instead of Python-style `#` comments.
// These simple structs match the JSON returned by the Python CLI.

struct ParsedQuery: Decodable {
    let raw_query: String
    let semantic_query: String
    let start_epoch: Int?
    let end_epoch: Int?
    let sort_mode: String
    let answer_mode: Bool
}

struct SearchResultDTO: Decodable, Identifiable, Hashable {
    let file_path: String
    let captured_at_local: String
    let score: Double
    let snippet: String
    let ocr_text_preview: String
    let thumbnail_path: String?

    var id: String { file_path }
}

struct AnswerCitationDTO: Decodable, Hashable, Identifiable {
    let footnote: Int
    let result_index: Int
    let file_path: String
    let captured_at_local: String
    let snippet: String

    var id: Int { footnote }
}

struct SearchResponseDTO: Decodable {
    let mode: String
    let parsed_query: ParsedQuery
    let filters_applied: [String]
    let answer: String?
    let citations: [AnswerCitationDTO]
    let results: [SearchResultDTO]
}

struct StatusDTO: Decodable {
    let screenshot_root: String
    let app_support_dir: String
    let database_path: String
    let screenshot_count: Int
    let chunk_count: Int
    let vec_enabled: Bool
    let last_successful_scan_at: String?
    let last_indexed_path: String?
}

enum QueryMode: String, CaseIterable, Identifiable {
    case semantic = "semantic"
    case ocrOnly = "ocr-only"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .semantic:
            return "Semantic"
        case .ocrOnly:
            return "OCR Only"
        }
    }
}
