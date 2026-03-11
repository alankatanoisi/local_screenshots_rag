from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from PIL import Image

from screenmemory.config import ScreenMemoryConfig
from screenmemory.db import Database, serialize_embedding
from screenmemory.gemini import GeminiClient
from screenmemory.ocr import chunk_text, run_tesseract


# This keeps the allowed embedding write modes obvious at the function boundary.
EmbeddingMode = Literal["sync", "batch", "skip"]


def _sha256_file(file_path: Path) -> str:
    # Hashing lets us detect true file-content changes without touching the source file.
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_timestamp(file_path: Path) -> int:
    # The filename itself is the authoritative capture timestamp.
    return int(file_path.stem)


def _is_timestamped_screenshot(file_path: Path) -> bool:
    # The real corpus includes some extra JPEGs that are not the regular 30-second captures.
    # We only ingest files that match the normal ScreenMemory capture layout:
    # .../YYYY/MM/DD/HH/<unix_timestamp>.jpeg
    stem = file_path.stem
    if not stem.isdigit() or len(stem) < 10:
        return False

    parent_parts = file_path.parts[-5:-1]
    if len(parent_parts) != 4:
        return False

    year, month, day, hour = parent_parts
    return (
        year.isdigit()
        and len(year) == 4
        and month.isdigit()
        and len(month) == 2
        and day.isdigit()
        and len(day) == 2
        and hour.isdigit()
        and len(hour) == 2
    )


def _iter_screenshots(
    root: Path,
    recent_days: int | None,
    mode: str,
) -> list[Path]:
    # Sorting by the filename timestamp keeps ordering independent from filesystem mtimes.
    files = [
        path
        for pattern in ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG")
        for path in root.rglob(pattern)
        if path.is_file()
        and not path.name.startswith(".")
        and _is_timestamped_screenshot(path)
    ]
    cutoff_epoch = None
    if recent_days is not None:
        cutoff_epoch = int((datetime.now() - timedelta(days=recent_days)).timestamp())

    if cutoff_epoch is not None and mode == "recent":
        files = [path for path in files if _source_timestamp(path) >= cutoff_epoch]
    elif cutoff_epoch is not None and mode == "backfill":
        files = [path for path in files if _source_timestamp(path) < cutoff_epoch]

    reverse = mode != "backfill"
    if mode == "all":
        reverse = False
    return sorted(files, key=_source_timestamp, reverse=reverse)


def _process_single_screenshot(
    db: Database,
    gemini: GeminiClient | None,
    config: ScreenMemoryConfig,
    image_path: Path,
    embedding_mode: EmbeddingMode,
) -> tuple[bool, str]:
    # This shared helper performs the actual OCR and database update for one screenshot.
    # Returning a boolean keeps the caller aware of whether this file was newly processed
    # or merely recognized as unchanged and skipped.
    stat = image_path.stat()
    sha256 = _sha256_file(image_path)
    existing = db.get_screenshot_by_path(str(image_path))

    if (
        existing is not None
        and existing["sha256"] == sha256
        and int(existing["source_mtime_ns"]) == stat.st_mtime_ns
    ):
        return False, str(existing["indexed_at"])

    # Pillow reads the image headers without changing the source file.
    with Image.open(image_path) as image:
        width, height = image.size

    ocr = run_tesseract(image_path)
    captured_at_epoch = _source_timestamp(image_path)
    captured_dt = datetime.fromtimestamp(captured_at_epoch)
    indexed_at = datetime.now().isoformat()

    screenshot_id = db.upsert_screenshot(
        {
            "file_path": str(image_path),
            "captured_at_epoch": captured_at_epoch,
            "captured_at_local_iso": captured_dt.isoformat(),
            "year": captured_dt.year,
            "month": captured_dt.month,
            "day": captured_dt.day,
            "hour": captured_dt.hour,
            "width": width,
            "height": height,
            "file_size": stat.st_size,
            "sha256": sha256,
            "source_mtime_ns": stat.st_mtime_ns,
            "ocr_text": ocr.text,
            "ocr_confidence_avg": ocr.confidence_avg,
            "indexed_at": indexed_at,
        }
    )

    chunk_records = []
    chunk_specs = chunk_text(ocr.text)
    embedding_dimensions = None

    for chunk_spec in chunk_specs:
        chunk_text_value = chunk_spec["text"].strip()
        embedding_blob = None
        embedding_status = "pending"
        embedding_batch_id = None

        if not chunk_text_value:
            # Empty OCR chunks can never produce meaningful embeddings,
            # so we mark them as skipped instead of leaving them pending forever.
            embedding_status = "skipped"
        if (
            embedding_mode == "sync"
            and gemini is not None
            and gemini.configured
            and chunk_text_value
        ):
            embedding = gemini.embed_text(
                chunk_spec["text"],
                task_type="RETRIEVAL_DOCUMENT",
            )
            embedding_blob = serialize_embedding(embedding)
            embedding_dimensions = len(embedding)
            embedding_status = "ready"
        elif embedding_mode == "skip":
            embedding_status = "skipped"
        elif embedding_mode == "batch":
            embedding_status = "pending"

        chunk_records.append(
            {
                "screenshot_id": screenshot_id,
                "chunk_index": chunk_spec["chunk_index"],
                "text": chunk_spec["text"],
                "start_offset": chunk_spec["start_offset"],
                "end_offset": chunk_spec["end_offset"],
                "embedding": embedding_blob,
                "token_count": chunk_spec["token_count"],
                "embedding_model": config.gemini_embedding_model,
                "embedding_status": embedding_status,
                "embedding_batch_id": embedding_batch_id,
                "embedding_updated_at": indexed_at,
            }
        )

    if embedding_dimensions:
        db.ensure_vector_table(embedding_dimensions)

    db.replace_chunks(screenshot_id, chunk_records)
    db.commit()
    return True, indexed_at


def run_index_pass(
    config: ScreenMemoryConfig,
    db: Database,
    gemini: GeminiClient | None,
    recent_days: int | None,
    batch_limit: int | None,
    mode: str,
    embedding_mode: EmbeddingMode = "sync",
) -> dict:
    # This is the heart of ingestion.
    # It reads screenshots, extracts OCR, stores metadata, and optionally stores embeddings.
    processed = 0
    skipped = 0
    errors = 0
    last_indexed_path = None
    last_indexed_at = datetime.now().isoformat()

    for image_path in _iter_screenshots(config.screenshot_root, recent_days, mode):
        if batch_limit is not None and processed >= batch_limit:
            break

        try:
            was_processed, indexed_at = _process_single_screenshot(
                db=db,
                gemini=gemini,
                config=config,
                image_path=image_path,
                embedding_mode=embedding_mode,
            )
            if not was_processed:
                skipped += 1
                continue

            processed += 1
            last_indexed_path = str(image_path)
            last_indexed_at = indexed_at
        except Exception as exc:
            errors += 1
            db.record_error(
                file_path=str(image_path),
                stage="index",
                message=str(exc),
                created_at=datetime.now().isoformat(),
            )

    db.record_state("last_successful_scan_at", datetime.now().isoformat())
    if last_indexed_path:
        db.record_state("last_indexed_path", last_indexed_path)
        db.record_state("last_indexed_at", last_indexed_at)

    return {
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "last_indexed_path": last_indexed_path,
    }


def run_full_index_chunk(
    config: ScreenMemoryConfig,
    db: Database,
    gemini: GeminiClient | None,
    batch_limit: int,
    embedding_mode: EmbeddingMode = "sync",
) -> dict:
    # This dedicated full-index pass walks the whole screenshot history in ascending timestamp order.
    # The cursor is stored in the database, so each future run resumes from the prior stopping point.
    last_cursor_text = db.get_state("full_index_last_cursor_epoch")
    last_cursor_epoch = int(last_cursor_text) if last_cursor_text else None

    processed = 0
    skipped = 0
    errors = 0
    last_indexed_path = None
    last_indexed_at = None
    last_seen_epoch = last_cursor_epoch
    scanned = 0

    for image_path in _iter_screenshots(config.screenshot_root, recent_days=None, mode="all"):
        image_epoch = _source_timestamp(image_path)
        if last_cursor_epoch is not None and image_epoch <= last_cursor_epoch:
            continue

        if scanned >= batch_limit:
            break

        scanned += 1
        last_seen_epoch = image_epoch

        try:
            was_processed, indexed_at = _process_single_screenshot(
                db=db,
                gemini=gemini,
                config=config,
                image_path=image_path,
                embedding_mode=embedding_mode,
            )
            if was_processed:
                processed += 1
                last_indexed_path = str(image_path)
                last_indexed_at = indexed_at
            else:
                skipped += 1

            db.record_state("full_index_last_cursor_epoch", str(image_epoch))
            db.record_state("full_index_last_cursor_path", str(image_path))
        except Exception as exc:
            errors += 1
            db.record_error(
                file_path=str(image_path),
                stage="full-index",
                message=str(exc),
                created_at=datetime.now().isoformat(),
            )
            # We still advance the cursor past a bad file so one failure does not stall the whole job.
            db.record_state("full_index_last_cursor_epoch", str(image_epoch))
            db.record_state("full_index_last_cursor_path", str(image_path))

    now_text = datetime.now().isoformat()
    db.record_state("last_successful_scan_at", now_text)

    remaining_estimate = sum(
        1
        for path in _iter_screenshots(config.screenshot_root, recent_days=None, mode="all")
        if last_seen_epoch is None or _source_timestamp(path) > last_seen_epoch
    )
    completed = remaining_estimate == 0

    if completed:
        db.record_state("full_index_completed_at", now_text)

    if last_indexed_path:
        db.record_state("last_indexed_path", last_indexed_path)
    if last_indexed_at:
        db.record_state("last_indexed_at", last_indexed_at)

    return {
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "last_indexed_path": last_indexed_path,
        "full_index_cursor_epoch": last_seen_epoch,
        "full_index_completed": completed,
        "remaining_estimate": remaining_estimate,
    }
