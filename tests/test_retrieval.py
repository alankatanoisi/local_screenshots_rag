from __future__ import annotations

from datetime import datetime

from screenmemory.db import Database, serialize_embedding
from screenmemory.models import AnswerCitation
from screenmemory.models import QueryPlan
from screenmemory.retrieval import search
from screenmemory.safety import ensure_runtime_directories
from screenmemory.thumbs import ThumbnailManager

from tests.helpers import make_test_image


class FakeGemini:
    # This fake client lets us test semantic mode without making network calls.
    configured = True

    def __init__(self, query_embedding: list[float]) -> None:
        self.query_embedding = query_embedding

    def plan_query(self, raw_query: str, now: datetime) -> QueryPlan:
        return QueryPlan(
            mode="semantic",
            raw_query=raw_query,
            semantic_query="tuition email",
            start_epoch=None,
            end_epoch=None,
            sort_mode="relevance",
            answer_mode=True,
            filters_applied=["fake planner"],
        )

    def embed_text(self, text: str, task_type: str) -> list[float]:
        return self.query_embedding

    def answer_with_context(self, question: str, results) -> tuple[str, list[AnswerCitation]]:
        return (
            "Fake Gemini answer [1]",
            [
                AnswerCitation(
                    footnote=1,
                    result_index=0,
                    file_path=results[0].file_path,
                    captured_at_local=results[0].captured_at_local,
                    snippet=results[0].snippet,
                )
            ],
        )


def _insert_screenshot(db: Database, path: str, captured_at_epoch: int, text: str, embedding: list[float]) -> None:
    screenshot_id = db.upsert_screenshot(
        {
            "file_path": path,
            "captured_at_epoch": captured_at_epoch,
            "captured_at_local_iso": datetime.fromtimestamp(captured_at_epoch).isoformat(),
            "year": datetime.fromtimestamp(captured_at_epoch).year,
            "month": datetime.fromtimestamp(captured_at_epoch).month,
            "day": datetime.fromtimestamp(captured_at_epoch).day,
            "hour": datetime.fromtimestamp(captured_at_epoch).hour,
            "width": 600,
            "height": 300,
            "file_size": 1234,
            "sha256": f"sha-{captured_at_epoch}",
            "source_mtime_ns": captured_at_epoch * 1_000_000_000,
            "ocr_text": text,
            "ocr_confidence_avg": 95.0,
            "indexed_at": datetime.now().isoformat(),
        }
    )
    db.replace_chunks(
        screenshot_id,
        [
            {
                "screenshot_id": screenshot_id,
                "chunk_index": 0,
                "text": text,
                "start_offset": 0,
                "end_offset": len(text),
                "embedding": serialize_embedding(embedding),
                "token_count": len(text.split()),
            }
        ],
    )
    db.commit()


def test_ocr_only_search_uses_local_fts(app_paths) -> None:
    ensure_runtime_directories(app_paths)
    first = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769392950.jpeg"
    second = app_paths.screenshot_root / "2026" / "01" / "25" / "19" / "1769396550.jpeg"
    make_test_image(first, "tuition email")
    make_test_image(second, "shopping list")

    db = Database(app_paths)
    try:
        _insert_screenshot(db, str(first), 1769392950, "tuition email draft", [1.0, 0.0, 0.0])
        _insert_screenshot(db, str(second), 1769396550, "shopping list", [0.0, 1.0, 0.0])
        response = search(
            raw_query="tuition email",
            mode="ocr-only",
            db=db,
            config=app_paths,
            gemini=None,
            thumbnail_manager=ThumbnailManager(app_paths),
            limit=5,
            sort_mode=None,
            start_epoch=None,
            end_epoch=None,
            answer_mode=False,
        )
    finally:
        db.close()

    assert response.answer is None
    assert response.results
    assert "tuition" in response.results[0].snippet.lower()


def test_semantic_search_returns_answer_and_respects_date_filters(app_paths) -> None:
    ensure_runtime_directories(app_paths)
    early = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769392950.jpeg"
    late = app_paths.screenshot_root / "2026" / "01" / "25" / "19" / "1769396550.jpeg"
    make_test_image(early, "tuition email")
    make_test_image(late, "shopping list")

    db = Database(app_paths)
    try:
        _insert_screenshot(db, str(early), 1769392950, "tuition email draft", [0.99, 0.01, 0.0])
        _insert_screenshot(db, str(late), 1769396550, "shopping list", [0.0, 1.0, 0.0])
        response = search(
            raw_query="find the tuition email",
            mode="semantic",
            db=db,
            config=app_paths,
            gemini=FakeGemini([1.0, 0.0, 0.0]),
            thumbnail_manager=ThumbnailManager(app_paths),
            limit=5,
            sort_mode="relevance",
            start_epoch=1769392000,
            end_epoch=1769394000,
            answer_mode=True,
        )
    finally:
        db.close()

    assert response.answer == "Fake Gemini answer [1]"
    assert len(response.results) == 1
    assert response.results[0].file_path.endswith("1769392950.jpeg")
    assert response.citations
    assert response.citations[0].footnote == 1
