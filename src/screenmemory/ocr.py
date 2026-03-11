from __future__ import annotations

import csv
import subprocess
from dataclasses import dataclass
from io import StringIO
from pathlib import Path


@dataclass(slots=True)
class OCRResult:
    # We keep both the combined text and a simple average confidence score.
    text: str
    confidence_avg: float


def run_tesseract(image_path: Path) -> OCRResult:
    # We call tesseract in TSV mode because TSV includes confidence values per token.
    # The screenshot file itself is opened read-only by tesseract.
    completed = subprocess.run(
        [
            "tesseract",
            str(image_path),
            "stdout",
            "--psm",
            "6",
            "tsv",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    rows = list(csv.DictReader(StringIO(completed.stdout), delimiter="\t"))
    words: list[str] = []
    confidences: list[float] = []

    for row in rows:
        text = (row.get("text") or "").strip()
        confidence_text = (row.get("conf") or "").strip()
        if not text:
            continue
        words.append(text)
        try:
            confidence_value = float(confidence_text)
        except ValueError:
            continue
        if confidence_value >= 0:
            confidences.append(confidence_value)

    joined_text = " ".join(words).strip()
    average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return OCRResult(text=joined_text, confidence_avg=average_confidence)


def chunk_text(text: str, target_chars: int = 550, overlap_chars: int = 80) -> list[dict]:
    # Chunking makes the semantic search more precise because each vector represents a smaller idea.
    normalized = " ".join(text.split())
    if not normalized:
        return []

    chunks: list[dict] = []
    start = 0
    chunk_index = 0

    while start < len(normalized):
        end = min(len(normalized), start + target_chars)
        if end < len(normalized):
            # We try to cut on whitespace so snippets stay readable.
            whitespace_cut = normalized.rfind(" ", start, end)
            if whitespace_cut > start + 100:
                end = whitespace_cut

        chunk_text_value = normalized[start:end].strip()
        if chunk_text_value:
            chunks.append(
                {
                    "chunk_index": chunk_index,
                    "text": chunk_text_value,
                    "start_offset": start,
                    "end_offset": end,
                    "token_count": max(1, len(chunk_text_value.split())),
                }
            )
            chunk_index += 1

        if end >= len(normalized):
            break

        start = max(end - overlap_chars, start + 1)

    return chunks
