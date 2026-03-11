from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from screenmemory.config import ScreenMemoryConfig
from screenmemory.db import Database


class BatchEmbeddingClient:
    # This helper is intentionally separate from the live Gemini client.
    # Live search needs fast request/response behavior.
    # Batch embedding is the opposite: slow, offline, and meant for large backfills.
    def __init__(self, config: ScreenMemoryConfig) -> None:
        self.config = config
        self.api_key = config.gemini_api_key
        self._sdk_client = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def client(self):
        # We import the SDK lazily so the rest of the app still loads
        # even if the user is only doing OCR-only search and never uses batch jobs.
        if self._sdk_client is None:
            if not self.api_key:
                raise RuntimeError(
                    "Gemini is not configured. Set GEMINI_API_KEY or GOOGLE_API_KEY first."
                )

            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover - exercised in live env, not tests
                raise RuntimeError(
                    "The google-genai package is required for batch embeddings. "
                    "In Terminal, open the project folder, activate .venv, and run "
                    "`uv pip install \".[dev,vec]\"` again."
                ) from exc

            self._sdk_client = genai.Client(api_key=self.api_key)
        return self._sdk_client

    def submit_pending_embeddings(self, db: Database, limit: int) -> dict[str, Any]:
        # This command grabs a slice of locally indexed OCR chunks that do not have embeddings yet,
        # writes a JSONL request file under app support, uploads it, and starts a Gemini batch job.
        pending_rows = db.fetch_pending_chunks_for_batch(limit)
        if not pending_rows:
            return {
                "submitted": False,
                "message": "No pending chunks for the active embedding model.",
                "chunk_count": 0,
            }

        created_at = datetime.now().isoformat()
        request_stem = datetime.now().strftime("embed-%Y%m%d-%H%M%S-%f")
        request_path = self.config.batch_requests_dir / f"{request_stem}.jsonl"
        manifest_path = self.config.batch_requests_dir / f"{request_stem}.manifest.json"

        chunk_ids = [int(row["id"]) for row in pending_rows]
        request_lines = []
        for row in pending_rows:
            request_lines.append(
                json.dumps(
                    {
                        # The key is not required for our importer because the output
                        # stays in request order, but keeping the chunk id here makes
                        # troubleshooting much easier if the user inspects the JSONL file.
                        "key": str(row["id"]),
                        "request": {
                            "content": {
                                "parts": [
                                    {
                                        "text": str(row["text"]),
                                    }
                                ]
                            },
                            "taskType": "RETRIEVAL_DOCUMENT",
                        },
                    }
                )
            )

        request_path.write_text("\n".join(request_lines) + "\n", encoding="utf-8")
        manifest_path.write_text(
            json.dumps(
                {
                    "batch_request_name": request_stem,
                    "created_at": created_at,
                    "embedding_model": self.config.gemini_embedding_model,
                    "chunk_ids": chunk_ids,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        uploaded_file = self.client.files.upload(
            file=request_path,
            config={
                "display_name": request_path.name,
                "mime_type": "application/jsonl",
            },
        )
        batch_job = self.client.batches.create_embeddings(
            model=self.config.gemini_embedding_model,
            src={"file_name": uploaded_file.name},
            config={"display_name": request_stem},
        )

        batch_name = str(batch_job.name)
        db.record_batch_job(
            {
                "batch_id": batch_name,
                "model": self.config.gemini_embedding_model,
                "local_request_path": str(request_path),
                "local_manifest_path": str(manifest_path),
                "local_result_path": None,
                "remote_input_file_name": getattr(uploaded_file, "name", None),
                "remote_output_file_name": self._batch_output_file_name(batch_job),
                "status": f"job_{self._normalize_job_state(getattr(batch_job, 'state', None))}",
                "chunk_count": len(chunk_ids),
                "submitted_at": created_at,
                "updated_at": created_at,
                "imported_at": None,
                "error_message": None,
            }
        )
        db.mark_chunks_submitted(chunk_ids, batch_name, created_at)

        return {
            "submitted": True,
            "batch_id": batch_name,
            "chunk_count": len(chunk_ids),
            "request_path": str(request_path),
            "manifest_path": str(manifest_path),
            "remote_input_file_name": getattr(uploaded_file, "name", None),
            "status": f"job_{self._normalize_job_state(getattr(batch_job, 'state', None))}",
        }

    def sync_batch_jobs(self, db: Database, batch_id: str | None = None) -> dict[str, Any]:
        # This importer checks one specific batch or all open batches,
        # downloads finished results, and writes embeddings back into SQLite.
        candidate_rows = []
        if batch_id:
            row = db.get_batch_job(batch_id)
            if row is None:
                raise RuntimeError(f"No batch job found for {batch_id}")
            candidate_rows = [row]
        else:
            candidate_rows = db.list_batch_jobs(only_open=True)

        summaries = []
        for row in candidate_rows:
            summaries.append(self._sync_single_batch_job(db, row))

        imported = sum(int(item.get("imported_ready", 0)) for item in summaries)
        failed = sum(int(item.get("imported_failed", 0)) for item in summaries)
        completed_jobs = sum(1 for item in summaries if item.get("completed"))
        return {
            "jobs_checked": len(summaries),
            "jobs_completed_now": completed_jobs,
            "imported_ready": imported,
            "imported_failed": failed,
            "jobs": summaries,
        }

    def cancel_batch_jobs(
        self,
        db: Database,
        *,
        batch_id: str | None = None,
        clear_pending: bool,
    ) -> dict[str, Any]:
        # This is the "stop everything" entry point for batch embeddings.
        #
        # There are two buckets of work to clean up:
        # 1. jobs that were already submitted to Gemini
        # 2. chunks that are still only queued locally as `pending`
        #
        # We handle both so the user's `status` screen actually drops to zero
        # instead of looking half-cancelled.
        candidate_rows = []
        if batch_id:
            row = db.get_batch_job(batch_id)
            if row is None:
                raise RuntimeError(f"No batch job found for {batch_id}")
            candidate_rows = [row]
        else:
            candidate_rows = db.list_batch_jobs(only_open=True)

        checked_at = datetime.now().isoformat()
        job_summaries = []
        submitted_chunks_cleared = 0
        warnings: list[str] = []

        for row in candidate_rows:
            summary = self._cancel_single_batch_job(db, row=row, checked_at=checked_at)
            job_summaries.append(summary)
            submitted_chunks_cleared += int(summary.get("submitted_chunks_cleared", 0))
            warning_text = summary.get("warning")
            if isinstance(warning_text, str) and warning_text:
                warnings.append(warning_text)

        pending_chunks_cleared = 0
        if clear_pending:
            pending_chunks_cleared = db.clear_pending_embeddings(checked_at)

        return {
            "jobs_requested": len(candidate_rows),
            "jobs_closed": sum(1 for item in job_summaries if item.get("closed")),
            "submitted_chunks_cleared": submitted_chunks_cleared,
            "pending_chunks_cleared": pending_chunks_cleared,
            "warnings": warnings,
            "jobs": job_summaries,
        }

    def _sync_single_batch_job(self, db: Database, row: Any) -> dict[str, Any]:
        batch_name = str(row["batch_id"])
        checked_at = datetime.now().isoformat()
        batch_job = self.client.batches.get(name=batch_name)
        normalized_state = self._normalize_job_state(getattr(batch_job, "state", None))
        status_text = f"job_{normalized_state}"
        output_file_name = self._batch_output_file_name(batch_job)
        error_message = self._job_error_text(batch_job)

        if normalized_state == "succeeded":
            # Once the remote job succeeds, we download the JSONL once and import it once.
            # After that, the local DB has what it needs and semantic search can use it.
            if row["imported_at"]:
                db.update_batch_job(
                    batch_name,
                    status="job_succeeded_imported",
                    updated_at=checked_at,
                    remote_output_file_name=output_file_name,
                    error_message=error_message,
                )
                return {
                    "batch_id": batch_name,
                    "status": "job_succeeded_imported",
                    "completed": False,
                    "imported_ready": 0,
                    "imported_failed": 0,
                }

            result_path = self._download_result_file(
                output_file_name=output_file_name,
                batch_name=batch_name,
            )
            manifest = json.loads(Path(row["local_manifest_path"]).read_text(encoding="utf-8"))
            chunk_ids = [int(chunk_id) for chunk_id in manifest["chunk_ids"]]
            embeddings = self._parse_result_embeddings(result_path, expected_count=len(chunk_ids))
            import_summary = db.apply_batch_embeddings(
                chunk_ids=chunk_ids,
                embeddings=embeddings,
                batch_id=batch_name,
                embedding_model=str(row["model"]),
                updated_at=checked_at,
            )
            db.update_batch_job(
                batch_name,
                status="job_succeeded_imported",
                updated_at=checked_at,
                remote_output_file_name=output_file_name,
                local_result_path=str(result_path),
                imported_at=checked_at,
                error_message=error_message,
            )
            return {
                "batch_id": batch_name,
                "status": "job_succeeded_imported",
                "completed": True,
                "imported_ready": import_summary["ready"],
                "imported_failed": import_summary["failed"],
            }

        if normalized_state in {"failed", "cancelled"}:
            manifest = json.loads(Path(row["local_manifest_path"]).read_text(encoding="utf-8"))
            chunk_ids = [int(chunk_id) for chunk_id in manifest["chunk_ids"]]
            db.mark_chunks_failed(chunk_ids, batch_name, checked_at)
            db.update_batch_job(
                batch_name,
                status=status_text,
                updated_at=checked_at,
                remote_output_file_name=output_file_name,
                error_message=error_message,
            )
            return {
                "batch_id": batch_name,
                "status": status_text,
                "completed": True,
                "imported_ready": 0,
                "imported_failed": len(chunk_ids),
            }

        db.update_batch_job(
            batch_name,
            status=status_text,
            updated_at=checked_at,
            remote_output_file_name=output_file_name,
            error_message=error_message,
        )
        return {
            "batch_id": batch_name,
            "status": status_text,
            "completed": False,
            "imported_ready": 0,
            "imported_failed": 0,
        }

    def _cancel_single_batch_job(
        self,
        db: Database,
        *,
        row: Any,
        checked_at: str,
    ) -> dict[str, Any]:
        # A remote batch can be in a few different states when we try to cancel it:
        # - still running
        # - already cancelled
        # - already failed
        # - already succeeded but not imported yet
        #
        # The user's intent is simple: "make this stop counting as active work."
        # So we close the local record either by syncing a real remote cancelled state,
        # or by falling back to a local closure with a warning if the SDK cannot cancel.
        batch_name = str(row["batch_id"])
        warning: str | None = None
        remote_cancel_requested = False

        try:
            remote_cancel_requested = self._request_remote_cancel(batch_name)
        except Exception as exc:
            # We do not want one remote API issue to strand the whole local queue.
            # Instead we surface the warning and still close the local work.
            warning = f"Remote cancel failed for {batch_name}: {exc}"

        normalized_state = "cancelled"
        output_file_name = None
        error_message = warning

        try:
            batch_job = self.client.batches.get(name=batch_name)
            normalized_state = self._normalize_job_state(getattr(batch_job, "state", None))
            output_file_name = self._batch_output_file_name(batch_job)
            error_message = self._job_error_text(batch_job) or warning
        except Exception as exc:
            # If we cannot even read the remote state, we still complete the local cancellation.
            # Using a local cancelled state is better than leaving the UI stuck on "open batch jobs".
            if warning is None:
                warning = f"Remote state refresh failed for {batch_name}: {exc}"
            error_message = warning

        # A finished remote job is not "open" anymore.
        # For this command we treat succeeded/failed/cancelled as terminal,
        # and we intentionally do not import successful results because the user asked to stop.
        terminal_state = normalized_state
        if terminal_state not in {"cancelled", "failed", "succeeded"}:
            terminal_state = "cancelled"

        submitted_chunks_cleared = db.cancel_chunks_for_batch(batch_name, checked_at)

        local_status = "job_cancelled" if terminal_state in {"cancelled", "succeeded"} else "job_failed"
        db.update_batch_job(
            batch_name,
            status=local_status,
            updated_at=checked_at,
            remote_output_file_name=output_file_name,
            error_message=error_message,
        )

        return {
            "batch_id": batch_name,
            "previous_status": str(row["status"]),
            "status": local_status,
            "closed": True,
            "remote_cancel_requested": remote_cancel_requested,
            "submitted_chunks_cleared": submitted_chunks_cleared,
            "warning": warning,
        }

    def _request_remote_cancel(self, batch_name: str) -> bool:
        # The installed Gemini SDK may or may not expose a batch cancel helper.
        # We probe for it at runtime instead of hard-coding one version's API shape.
        batches_api = self.client.batches
        cancel_method = getattr(batches_api, "cancel", None)
        if callable(cancel_method):
            cancel_method(name=batch_name)
            return True
        return False

    def _download_result_file(self, output_file_name: str | None, batch_name: str) -> Path:
        if not output_file_name:
            raise RuntimeError(f"Batch job {batch_name} succeeded but has no output file name.")

        output_bytes = self.client.files.download(file=output_file_name)
        safe_batch_name = batch_name.replace("/", "_")
        result_path = self.config.batch_results_dir / f"{safe_batch_name}.jsonl"
        result_path.write_bytes(output_bytes)
        return result_path

    def _parse_result_embeddings(
        self,
        result_path: Path,
        expected_count: int,
    ) -> list[list[float] | None]:
        # The API writes one JSON object per line.
        # The batch docs say output order matches input order, so we rely on that ordering.
        embeddings: list[list[float] | None] = []
        for raw_line in result_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            embeddings.append(self._extract_embedding_values(parsed))

        if len(embeddings) < expected_count:
            embeddings.extend([None] * (expected_count - len(embeddings)))
        elif len(embeddings) > expected_count:
            embeddings = embeddings[:expected_count]

        return embeddings

    def _extract_embedding_values(self, parsed_line: dict[str, Any]) -> list[float] | None:
        response = parsed_line.get("response")
        if isinstance(response, dict):
            if isinstance(response.get("embedding"), dict):
                values = response["embedding"].get("values")
                if isinstance(values, list):
                    return [float(value) for value in values]
            embeddings = response.get("embeddings")
            if isinstance(embeddings, list) and embeddings:
                first = embeddings[0]
                if isinstance(first, dict):
                    values = first.get("values")
                    if isinstance(values, list):
                        return [float(value) for value in values]

        if isinstance(parsed_line.get("embedding"), dict):
            values = parsed_line["embedding"].get("values")
            if isinstance(values, list):
                return [float(value) for value in values]

        return None

    def _batch_output_file_name(self, batch_job: Any) -> str | None:
        dest = getattr(batch_job, "dest", None)
        if dest is None:
            return None
        return getattr(dest, "file_name", None)

    def _job_error_text(self, batch_job: Any) -> str | None:
        error = getattr(batch_job, "error", None)
        if error is None:
            return None
        code = getattr(error, "code", None)
        message = getattr(error, "message", None)
        if code and message:
            return f"{code}: {message}"
        if message:
            return str(message)
        return str(error)

    def _normalize_job_state(self, state: Any) -> str:
        if state is None:
            return "unknown"
        name = getattr(state, "name", None)
        if name:
            state_text = str(name)
        else:
            state_text = str(state)
        state_text = state_text.strip().lower()
        state_text = state_text.replace("job_state_", "")
        return state_text
