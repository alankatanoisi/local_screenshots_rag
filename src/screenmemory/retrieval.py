from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime

from screenmemory.config import ScreenMemoryConfig
from screenmemory.db import Database, deserialize_embedding, serialize_embedding
from screenmemory.gemini import GeminiClient
from screenmemory.models import AnswerCitation, QueryPlan, SearchResponse, SearchResult
from screenmemory.thumbs import ThumbnailManager
from screenmemory.timeparse import parse_local_time_window


def _sanitize_fts_query(raw_query: str) -> str:
    # FTS5 has its own query syntax, so we strip punctuation that would otherwise break the search.
    tokens = re.findall(r"[A-Za-z0-9_@.-]+", raw_query)
    return " ".join(tokens[:12]) or raw_query.strip()


def _preview(text: str, max_chars: int = 220) -> str:
    normalized = " ".join(text.split())
    return normalized[:max_chars] + ("..." if len(normalized) > max_chars else "")


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def build_query_plan(
    raw_query: str,
    mode: str,
    config: ScreenMemoryConfig,
    gemini: GeminiClient | None,
    sort_mode: str | None,
    start_epoch: int | None,
    end_epoch: int | None,
    answer_mode: bool,
) -> QueryPlan:
    now = datetime.now()

    if mode == "semantic":
        if gemini is None or not gemini.configured:
            raise RuntimeError(
                "Semantic mode needs Gemini. Set GEMINI_API_KEY or use --mode ocr-only."
            )
        plan = gemini.plan_query(raw_query, now)
        if sort_mode:
            plan.sort_mode = sort_mode  # type: ignore[assignment]
        if start_epoch is not None:
            plan.start_epoch = start_epoch
        if end_epoch is not None:
            plan.end_epoch = end_epoch
        plan.answer_mode = answer_mode
        return plan

    local_start, local_end, local_filters = parse_local_time_window(
        raw_query,
        timezone_name=config.timezone_name,
        now=now,
    )
    final_start = start_epoch if start_epoch is not None else local_start
    final_end = end_epoch if end_epoch is not None else local_end
    filters = local_filters.copy()
    if sort_mode:
        filters.append(f"sort={sort_mode}")
    return QueryPlan(
        mode="ocr-only",
        raw_query=raw_query,
        semantic_query=raw_query,
        start_epoch=final_start,
        end_epoch=final_end,
        sort_mode=(sort_mode or "relevance"),  # type: ignore[arg-type]
        answer_mode=False,
        filters_applied=filters,
    )


def _result_sort_key(sort_mode: str, item: dict) -> tuple:
    if sort_mode == "newest":
        return (-item["captured_at_epoch"], -item["score"])
    if sort_mode == "oldest":
        return (item["captured_at_epoch"], -item["score"])
    return (-item["score"], -item["captured_at_epoch"])


def search(
    raw_query: str,
    mode: str,
    db: Database,
    config: ScreenMemoryConfig,
    gemini: GeminiClient | None,
    thumbnail_manager: ThumbnailManager,
    limit: int,
    sort_mode: str | None,
    start_epoch: int | None,
    end_epoch: int | None,
    answer_mode: bool,
) -> SearchResponse:
    # This top-level function is the single retrieval entry point used by both the CLI and the Swift app.
    plan = build_query_plan(
        raw_query=raw_query,
        mode=mode,
        config=config,
        gemini=gemini,
        sort_mode=sort_mode,
        start_epoch=start_epoch,
        end_epoch=end_epoch,
        answer_mode=answer_mode,
    )

    lexical_rows = db.search_fts_chunks(
        fts_query=_sanitize_fts_query(plan.semantic_query),
        start_epoch=plan.start_epoch,
        end_epoch=plan.end_epoch,
        limit=max(limit * 4, 20),
    )

    grouped: dict[int, dict] = defaultdict(
        lambda: {
            "file_path": "",
            "captured_at_epoch": 0,
            "captured_at_local": "",
            "score": 0.0,
            "snippet": "",
            "ocr_text_preview": "",
        }
    )

    for row in lexical_rows:
        lexical_score = 1.0 / (1.0 + abs(float(row["lexical_score"])))
        bucket = grouped[int(row["screenshot_id"])]
        bucket["file_path"] = row["file_path"]
        bucket["captured_at_epoch"] = int(row["captured_at_epoch"])
        bucket["captured_at_local"] = row["captured_at_local_iso"]
        bucket["ocr_text_preview"] = _preview(row["ocr_text"])
        if lexical_score > bucket["score"]:
            bucket["score"] = lexical_score
            bucket["snippet"] = _preview(row["text"])

    if mode == "semantic":
        assert gemini is not None
        query_embedding = gemini.embed_text(plan.semantic_query, task_type="RETRIEVAL_QUERY")
        query_blob = serialize_embedding(query_embedding)
        vec_rows = db.vec_search(query_blob, limit=max(limit * 8, 40))

        if vec_rows:
            detailed_rows = db.load_chunk_rows([int(row["chunk_id"]) for row in vec_rows])
            distance_map = {int(row["chunk_id"]): float(row["distance"]) for row in vec_rows}
            for row in detailed_rows:
                bucket = grouped[int(row["screenshot_id"])]
                score = 1.0 / (1.0 + distance_map[int(row["chunk_id"])])
                bucket["file_path"] = row["file_path"]
                bucket["captured_at_epoch"] = int(row["captured_at_epoch"])
                bucket["captured_at_local"] = row["captured_at_local_iso"]
                bucket["ocr_text_preview"] = _preview(row["ocr_text"])
                if score > bucket["score"]:
                    bucket["score"] = score
                    bucket["snippet"] = _preview(row["text"])
        else:
            fallback_rows = db.fetch_embeddings_for_filtered_chunks(
                start_epoch=plan.start_epoch,
                end_epoch=plan.end_epoch,
            )
            for row in fallback_rows:
                embedding_blob = row["embedding"]
                if embedding_blob is None:
                    continue
                score = _cosine_similarity(
                    query_embedding,
                    deserialize_embedding(embedding_blob),
                )
                bucket = grouped[int(row["screenshot_id"])]
                bucket["file_path"] = row["file_path"]
                bucket["captured_at_epoch"] = int(row["captured_at_epoch"])
                bucket["captured_at_local"] = row["captured_at_local_iso"]
                bucket["ocr_text_preview"] = _preview(row["ocr_text"])
                if score > bucket["score"]:
                    bucket["score"] = score
                    bucket["snippet"] = _preview(row["text"])

    ranked = sorted(grouped.values(), key=lambda item: _result_sort_key(plan.sort_mode, item))
    top_ranked = ranked[:limit]

    results = [
        SearchResult(
            file_path=item["file_path"],
            captured_at_local=item["captured_at_local"],
            score=round(float(item["score"]), 4),
            snippet=item["snippet"],
            ocr_text_preview=item["ocr_text_preview"],
            thumbnail_path=thumbnail_manager.get_or_create(item["file_path"]),
        )
        for item in top_ranked
    ]

    answer = None
    citations: list[AnswerCitation] = []
    if mode == "semantic" and plan.answer_mode and gemini is not None:
        if results:
            answer, citations = gemini.answer_with_context(raw_query, results)

    return SearchResponse(
        mode=plan.mode,
        parsed_query={
            "raw_query": plan.raw_query,
            "semantic_query": plan.semantic_query,
            "start_epoch": plan.start_epoch,
            "end_epoch": plan.end_epoch,
            "sort_mode": plan.sort_mode,
            "answer_mode": plan.answer_mode,
        },
        filters_applied=plan.filters_applied,
        answer=answer,
        citations=citations,
        results=results,
    )
