from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


# These Literal values keep the allowed mode names in one place.
QueryMode = Literal["semantic", "ocr-only"]
SortMode = Literal["relevance", "newest", "oldest"]


@dataclass(slots=True)
class ScreenshotRecord:
    # This object represents one source screenshot plus the OCR we extracted from it.
    file_path: Path
    captured_at_epoch: int
    captured_at_local_iso: str
    year: int
    month: int
    day: int
    hour: int
    width: int
    height: int
    file_size: int
    sha256: str
    source_mtime_ns: int
    ocr_text: str
    ocr_confidence_avg: float
    indexed_at: str


@dataclass(slots=True)
class TextChunk:
    # Each screenshot can become multiple text chunks so semantic search can aim at smaller units.
    screenshot_id: int
    chunk_index: int
    text: str
    start_offset: int
    end_offset: int
    embedding: bytes | None
    token_count: int


@dataclass(slots=True)
class QueryPlan:
    # The retrieval layer uses this normalized plan instead of re-parsing the raw user query everywhere.
    mode: QueryMode
    raw_query: str
    semantic_query: str
    start_epoch: int | None = None
    end_epoch: int | None = None
    sort_mode: SortMode = "relevance"
    answer_mode: bool = True
    filters_applied: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SearchResult:
    # This is the clean result shape returned to both the CLI and the Swift app.
    file_path: str
    captured_at_local: str
    score: float
    snippet: str
    ocr_text_preview: str
    thumbnail_path: str | None = None


@dataclass(slots=True)
class AnswerCitation:
    # Each footnote points back to one retrieved screenshot so the UI can map [1], [2], etc. to images.
    footnote: int
    result_index: int
    file_path: str
    captured_at_local: str
    snippet: str


@dataclass(slots=True)
class SearchResponse:
    # The top-level query response keeps both the parsed plan and the actual result list together.
    mode: QueryMode
    parsed_query: dict
    filters_applied: list[str]
    answer: str | None
    citations: list[AnswerCitation]
    results: list[SearchResult]
