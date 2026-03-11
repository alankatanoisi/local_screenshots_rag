from __future__ import annotations

from screenmemory.db import Database
from screenmemory.ingest import run_full_index_chunk, run_index_pass
from screenmemory.ocr import OCRResult
from screenmemory.safety import ensure_runtime_directories

from tests.helpers import make_test_image


def test_indexing_uses_filename_epoch_and_skips_unchanged(monkeypatch, app_paths) -> None:
    ensure_runtime_directories(app_paths)
    screenshot = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769392950.jpeg"
    make_test_image(screenshot, "hello world")

    monkeypatch.setattr(
        "screenmemory.ingest.run_tesseract",
        lambda _path: OCRResult(text="hello world", confidence_avg=91.0),
    )

    db = Database(app_paths)
    try:
        first = run_index_pass(
            config=app_paths,
            db=db,
            gemini=None,
            recent_days=None,
            batch_limit=None,
            mode="recent",
            embedding_mode="skip",
        )
        second = run_index_pass(
            config=app_paths,
            db=db,
            gemini=None,
            recent_days=None,
            batch_limit=None,
            mode="recent",
            embedding_mode="skip",
        )
        row = db.get_screenshot_by_path(str(screenshot))
    finally:
        db.close()

    assert first["processed"] == 1
    assert second["processed"] == 0
    assert second["skipped"] == 1
    assert row is not None
    assert int(row["captured_at_epoch"]) == 1769392950
    assert row["ocr_text"] == "hello world"


def test_indexing_ignores_non_timestamp_jpegs(monkeypatch, app_paths) -> None:
    ensure_runtime_directories(app_paths)
    good = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769392950.jpeg"
    extra = app_paths.screenshot_root / "2026" / "JPEG Images" / "some exported image.jpeg"
    make_test_image(good, "good capture")
    make_test_image(extra, "should be ignored")

    monkeypatch.setattr(
        "screenmemory.ingest.run_tesseract",
        lambda _path: OCRResult(text="good capture", confidence_avg=88.0),
    )

    db = Database(app_paths)
    try:
        summary = run_index_pass(
            config=app_paths,
            db=db,
            gemini=None,
            recent_days=None,
            batch_limit=None,
            mode="recent",
            embedding_mode="skip",
        )
    finally:
        db.close()

    assert summary["processed"] == 1


def test_indexing_ignores_numeric_but_malformed_capture_paths(monkeypatch, app_paths) -> None:
    ensure_runtime_directories(app_paths)
    good = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769392950.jpeg"
    malformed = app_paths.screenshot_root / "2025" / "12" / "01" / "22" / "22.jpeg"
    make_test_image(good, "good capture")
    make_test_image(malformed, "bad capture")

    monkeypatch.setattr(
        "screenmemory.ingest.run_tesseract",
        lambda _path: OCRResult(text="good capture", confidence_avg=88.0),
    )

    db = Database(app_paths)
    try:
        summary = run_index_pass(
            config=app_paths,
            db=db,
            gemini=None,
            recent_days=None,
            batch_limit=None,
            mode="recent",
            embedding_mode="skip",
        )
    finally:
        db.close()

    assert summary["processed"] == 1


def test_full_index_chunk_resumes_until_complete(monkeypatch, app_paths) -> None:
    ensure_runtime_directories(app_paths)
    first = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769392950.jpeg"
    second = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769392980.jpeg"
    third = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769393010.jpeg"
    make_test_image(first, "first capture")
    make_test_image(second, "second capture")
    make_test_image(third, "third capture")

    monkeypatch.setattr(
        "screenmemory.ingest.run_tesseract",
        lambda path: OCRResult(text=path.stem, confidence_avg=90.0),
    )

    db = Database(app_paths)
    try:
        first_run = run_full_index_chunk(
            config=app_paths,
            db=db,
            gemini=None,
            batch_limit=1,
            embedding_mode="skip",
        )
        second_run = run_full_index_chunk(
            config=app_paths,
            db=db,
            gemini=None,
            batch_limit=1,
            embedding_mode="skip",
        )
        third_run = run_full_index_chunk(
            config=app_paths,
            db=db,
            gemini=None,
            batch_limit=1,
            embedding_mode="skip",
        )
    finally:
        db.close()

    assert first_run["processed"] == 1
    assert first_run["full_index_completed"] is False
    assert str(first.name) in str(first_run["last_indexed_path"])
    assert second_run["processed"] == 1
    assert str(second.name) in str(second_run["last_indexed_path"])
    assert third_run["processed"] == 1
    assert third_run["full_index_completed"] is True
    assert str(third.name) in str(third_run["last_indexed_path"])
