from __future__ import annotations

import hashlib
import os
from pathlib import Path

from screenmemory.db import Database
from screenmemory.ingest import run_index_pass
from screenmemory.ocr import OCRResult
from screenmemory.safety import ensure_runtime_directories, ensure_safe_storage_paths

from tests.helpers import make_test_image


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _list_xattrs(path: Path) -> list[str]:
    # Some Python builds expose xattr helpers on `os`, while others do not.
    # The safety test should still run either way.
    listxattr = getattr(os, "listxattr", None)
    if listxattr is None:
        return []
    return listxattr(path)


def test_rejects_app_storage_inside_source_tree(app_paths) -> None:
    app_paths.app_support_dir = app_paths.screenshot_root / "bad-output"
    app_paths.database_path = app_paths.app_support_dir / "screenmemory.db"
    app_paths.thumbnail_cache_dir = app_paths.app_support_dir / "thumbnails"
    app_paths.log_dir = app_paths.app_support_dir / "logs"
    try:
        ensure_safe_storage_paths(app_paths)
        raised = False
    except ValueError:
        raised = True
    assert raised is True


def test_indexing_does_not_modify_source_files(monkeypatch, app_paths) -> None:
    ensure_runtime_directories(app_paths)
    screenshot = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769392950.jpeg"
    make_test_image(screenshot, "tuition email")

    before_hash = _sha256(screenshot)
    before_mtime_ns = screenshot.stat().st_mtime_ns
    before_paths = sorted(
        str(path.relative_to(app_paths.screenshot_root))
        for path in app_paths.screenshot_root.rglob("*")
    )
    before_xattrs = _list_xattrs(screenshot)

    monkeypatch.setattr(
        "screenmemory.ingest.run_tesseract",
        lambda _path: OCRResult(text="tuition email", confidence_avg=97.0),
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

    after_hash = _sha256(screenshot)
    after_mtime_ns = screenshot.stat().st_mtime_ns
    after_paths = sorted(
        str(path.relative_to(app_paths.screenshot_root))
        for path in app_paths.screenshot_root.rglob("*")
    )
    after_xattrs = _list_xattrs(screenshot)

    assert summary["processed"] == 1
    assert before_hash == after_hash
    assert before_mtime_ns == after_mtime_ns
    assert before_paths == after_paths
    assert before_xattrs == after_xattrs
