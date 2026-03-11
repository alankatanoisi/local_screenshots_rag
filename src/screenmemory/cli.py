from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from screenmemory.batch_embeddings import BatchEmbeddingClient
from screenmemory.config import load_config
from screenmemory.db import Database
from screenmemory.gemini import GeminiClient
from screenmemory.ingest import run_full_index_chunk, run_index_pass
from screenmemory.launchd import (
    install_full_index_launch_agent,
    install_launch_agent,
    remove_full_index_launch_agent,
    remove_launch_agent,
)
from screenmemory.models import SearchResponse
from screenmemory.retrieval import search
from screenmemory.safety import ensure_runtime_directories
from screenmemory.thumbs import ThumbnailManager
from screenmemory.timeparse import parse_explicit_datetime


def _parser() -> argparse.ArgumentParser:
    # argparse keeps the CLI dependency-free and easy to inspect.
    parser = argparse.ArgumentParser(prog="screenmemory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Index recent screenshots.")
    index_parser.add_argument("--recent-days", type=int, default=None)
    index_parser.add_argument("--batch-limit", type=int, default=200)
    index_parser.add_argument("--skip-embeddings", action="store_true")
    index_parser.add_argument("--batch-embeddings", action="store_true")

    backfill_parser = subparsers.add_parser("backfill", help="Backfill older screenshots.")
    backfill_parser.add_argument("--batch-limit", type=int, default=200)
    backfill_parser.add_argument("--recent-days", type=int, default=None)
    backfill_parser.add_argument("--skip-embeddings", action="store_true")
    backfill_parser.add_argument("--batch-embeddings", action="store_true")

    full_index_parser = subparsers.add_parser(
        "index-everything",
        help="Safely index the whole screenshot history in resumable chunks.",
    )
    full_index_parser.add_argument("--batch-limit", type=int, default=200)
    full_index_parser.add_argument("--skip-embeddings", action="store_true")
    full_index_parser.add_argument("--batch-embeddings", action="store_true")
    full_index_parser.add_argument("--background", action="store_true")
    full_index_parser.add_argument("--stop-agent-when-done", action="store_true")

    batch_submit_parser = subparsers.add_parser(
        "embed-batch-submit",
        help="Submit pending OCR chunks to Gemini Batch API for embeddings.",
    )
    batch_submit_parser.add_argument("--limit", type=int, default=500)

    batch_sync_parser = subparsers.add_parser(
        "embed-batch-sync",
        help="Poll Gemini Batch API jobs and import finished embeddings.",
    )
    batch_sync_parser.add_argument("--batch-id", type=str, default=None)
    batch_sync_parser.add_argument("--json", action="store_true")

    batch_cancel_parser = subparsers.add_parser(
        "cancel-batches",
        help="Cancel open batch embedding jobs and optionally clear the local queue.",
    )
    batch_cancel_parser.add_argument("--batch-id", type=str, default=None)
    batch_cancel_parser.add_argument("--all", action="store_true")
    batch_cancel_parser.add_argument("--clear-pending", action="store_true")
    batch_cancel_parser.add_argument("--json", action="store_true")

    query_parser = subparsers.add_parser("query", help="Search indexed screenshots.")
    query_parser.add_argument("query", type=str)
    query_parser.add_argument("--mode", choices=["semantic", "ocr-only"], default="ocr-only")
    query_parser.add_argument("--sort", choices=["relevance", "newest", "oldest"], default=None)
    query_parser.add_argument("--limit", type=int, default=None)
    query_parser.add_argument("--start", type=str, default=None)
    query_parser.add_argument("--end", type=str, default=None)
    query_parser.add_argument("--json", action="store_true")
    query_parser.add_argument("--no-answer", action="store_true")

    status_parser = subparsers.add_parser("status", help="Show database and config status.")
    status_parser.add_argument("--json", action="store_true")
    subparsers.add_parser("install-launch-agent", help="Install a macOS launch agent.")
    subparsers.add_parser("remove-launch-agent", help="Remove the macOS launch agent.")
    subparsers.add_parser(
        "remove-full-index-agent",
        help="Remove the dedicated full-index background launch agent.",
    )
    return parser


def _print_status(config, db: Database) -> None:
    status = db.status()
    print(f"Screenshot root: {config.screenshot_root}")
    print(f"App support dir: {config.app_support_dir}")
    print(f"Database path: {status['database_path']}")
    print(f"Indexed screenshots: {status['screenshot_count']}")
    print(f"Indexed chunks: {status['chunk_count']}")
    print(f"Pending embeddings ({config.gemini_embedding_model}): {status['pending_embedding_count']}")
    print(f"Open batch jobs: {status['open_batch_job_count']}")
    print(f"sqlite-vec enabled: {status['vec_enabled']}")
    print(f"Last successful scan: {status['last_successful_scan_at']}")
    print(f"Last indexed path: {status['last_indexed_path']}")
    print(f"Full index cursor epoch: {status['full_index_last_cursor_epoch']}")
    print(f"Full index cursor path: {status['full_index_last_cursor_path']}")
    print(f"Full index completed at: {status['full_index_completed_at']}")


def _status_payload(config, db: Database) -> dict:
    # This JSON-friendly shape is what the Swift app decodes.
    status = db.status()
    return {
        "screenshot_root": str(config.screenshot_root),
        "app_support_dir": str(config.app_support_dir),
        "database_path": status["database_path"],
        "screenshot_count": status["screenshot_count"],
        "chunk_count": status["chunk_count"],
        "pending_embedding_count": status["pending_embedding_count"],
        "open_batch_job_count": status["open_batch_job_count"],
        "vec_enabled": status["vec_enabled"],
        "last_successful_scan_at": status["last_successful_scan_at"],
        "last_indexed_path": status["last_indexed_path"],
        "full_index_last_cursor_epoch": status["full_index_last_cursor_epoch"],
        "full_index_last_cursor_path": status["full_index_last_cursor_path"],
        "full_index_completed_at": status["full_index_completed_at"],
    }


def _print_search_response(response: SearchResponse) -> None:
    print(f"Mode: {response.mode}")
    print(f"Filters applied: {', '.join(response.filters_applied) if response.filters_applied else 'none'}")
    if response.answer:
        print("\nGemini answer:\n")
        print(response.answer)
    print("\nTop results:\n")
    for index, result in enumerate(response.results, start=1):
        print(f"{index}. {result.captured_at_local} | score={result.score}")
        print(f"   Path: {result.file_path}")
        print(f"   Snippet: {result.snippet}")
        print(f"   OCR Preview: {result.ocr_text_preview}")
        print(f"   Thumbnail: {result.thumbnail_path}")
        print()


def _resolve_embedding_mode(args: argparse.Namespace) -> str:
    # These two flags overlap conceptually, so we reject the confusing combination.
    if getattr(args, "skip_embeddings", False) and getattr(args, "batch_embeddings", False):
        raise SystemExit("Choose either --skip-embeddings or --batch-embeddings, not both.")
    if getattr(args, "skip_embeddings", False):
        return "skip"
    if getattr(args, "batch_embeddings", False):
        return "batch"
    return "sync"


def _validate_batch_cancel_args(args: argparse.Namespace) -> None:
    # This command needs a target.
    # We force the choice here so the user cannot accidentally run
    # a vague cancel command and wonder why nothing happened.
    if args.all and args.batch_id:
        raise SystemExit("Choose either --all or --batch-id, not both.")
    if not args.all and not args.batch_id:
        raise SystemExit("Choose --all to cancel every open batch, or pass --batch-id.")


def main() -> None:
    # The CLI always loads config, applies the safety guard, and then opens the database.
    args = _parser().parse_args()
    config = load_config()
    ensure_runtime_directories(config)
    db = Database(config)
    gemini = GeminiClient(config)
    batch_embeddings = BatchEmbeddingClient(config)
    thumbnail_manager = ThumbnailManager(config)

    try:
        if args.command == "index":
            summary = run_index_pass(
                config=config,
                db=db,
                gemini=gemini if gemini.configured else None,
                recent_days=args.recent_days or config.default_recent_days,
                batch_limit=args.batch_limit,
                mode="recent",
                embedding_mode=_resolve_embedding_mode(args),
            )
            print(json.dumps(summary, indent=2))
            return

        if args.command == "backfill":
            summary = run_index_pass(
                config=config,
                db=db,
                gemini=gemini if gemini.configured else None,
                recent_days=args.recent_days or config.default_recent_days,
                batch_limit=args.batch_limit,
                mode="backfill",
                embedding_mode=_resolve_embedding_mode(args),
            )
            print(json.dumps(summary, indent=2))
            return

        if args.command == "index-everything":
            embedding_mode = _resolve_embedding_mode(args)
            if args.background:
                project_root = str(Path(__file__).resolve().parents[2])
                plist_path = install_full_index_launch_agent(
                    config=config,
                    project_root=project_root,
                    batch_limit=args.batch_limit,
                    skip_embeddings=embedding_mode == "skip",
                    batch_embeddings=embedding_mode == "batch",
                )
                print(f"Installed full-index launch agent: {plist_path}")
                return

            summary = run_full_index_chunk(
                config=config,
                db=db,
                gemini=gemini if gemini.configured else None,
                batch_limit=args.batch_limit,
                embedding_mode=embedding_mode,
            )
            print(json.dumps(summary, indent=2))

            if args.stop_agent_when_done and summary["full_index_completed"]:
                remove_full_index_launch_agent(config)

            return

        if args.command == "embed-batch-submit":
            summary = batch_embeddings.submit_pending_embeddings(db=db, limit=args.limit)
            print(json.dumps(summary, indent=2))
            return

        if args.command == "embed-batch-sync":
            summary = batch_embeddings.sync_batch_jobs(db=db, batch_id=args.batch_id)
            print(json.dumps(summary, indent=2))
            return

        if args.command == "cancel-batches":
            _validate_batch_cancel_args(args)
            summary = batch_embeddings.cancel_batch_jobs(
                db=db,
                batch_id=args.batch_id,
                clear_pending=args.clear_pending,
            )
            print(json.dumps(summary, indent=2))
            return

        if args.command == "query":
            response = search(
                raw_query=args.query,
                mode=args.mode,
                db=db,
                config=config,
                gemini=gemini if gemini.configured else None,
                thumbnail_manager=thumbnail_manager,
                limit=args.limit or config.default_query_limit,
                sort_mode=args.sort,
                start_epoch=parse_explicit_datetime(args.start, config.timezone_name),
                end_epoch=parse_explicit_datetime(args.end, config.timezone_name),
                answer_mode=not args.no_answer,
            )
            if args.json:
                print(json.dumps(asdict(response), indent=2))
            else:
                _print_search_response(response)
            return

        if args.command == "status":
            if args.json:
                print(json.dumps(_status_payload(config, db), indent=2))
            else:
                _print_status(config, db)
            return

        if args.command == "install-launch-agent":
            project_root = str(Path(__file__).resolve().parents[2])
            plist_path = install_launch_agent(config, project_root)
            print(f"Installed launch agent: {plist_path}")
            return

        if args.command == "remove-launch-agent":
            plist_path = remove_launch_agent(config)
            print(f"Removed launch agent: {plist_path}")
            return

        if args.command == "remove-full-index-agent":
            plist_path = remove_full_index_launch_agent(config)
            print(f"Removed full-index launch agent: {plist_path}")
            return
    finally:
        db.close()
