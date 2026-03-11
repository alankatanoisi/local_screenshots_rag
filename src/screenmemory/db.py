from __future__ import annotations

import sqlite3
from array import array
from datetime import datetime
from pathlib import Path
from typing import Any

from screenmemory.config import ScreenMemoryConfig


def serialize_embedding(values: list[float]) -> bytes:
    # We store float32 bytes so the data is compact and can also be reused by sqlite-vec if available.
    return array("f", values).tobytes()


def deserialize_embedding(blob: bytes) -> list[float]:
    # Turning the bytes back into Python floats is needed for the manual vector-search fallback.
    decoded = array("f")
    decoded.frombytes(blob)
    return list(decoded)


class Database:
    def __init__(self, config: ScreenMemoryConfig) -> None:
        # SQLite is the single local database for metadata, OCR, FTS, and optional vector search.
        self.config = config
        self.conn = sqlite3.connect(config.database_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self.vec_enabled = False
        self._load_vec_extension_if_available()
        self._create_schema()

    def close(self) -> None:
        self.conn.close()

    def _load_vec_extension_if_available(self) -> None:
        # sqlite-vec is optional.
        # If it is missing, the rest of the app still works and semantic search falls back to Python scoring.
        try:
            import sqlite_vec  # type: ignore

            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
            self.vec_enabled = True
        except Exception:
            self.vec_enabled = False
        finally:
            try:
                self.conn.enable_load_extension(False)
            except Exception:
                pass

    def _create_schema(self) -> None:
        # The main screenshot table keeps one row per source image.
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL UNIQUE,
                captured_at_epoch INTEGER NOT NULL,
                captured_at_local_iso TEXT NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                day INTEGER NOT NULL,
                hour INTEGER NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                file_size INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                source_mtime_ns INTEGER NOT NULL,
                ocr_text TEXT NOT NULL,
                ocr_confidence_avg REAL NOT NULL,
                indexed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                screenshot_id INTEGER NOT NULL REFERENCES screenshots(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                start_offset INTEGER NOT NULL,
                end_offset INTEGER NOT NULL,
                embedding BLOB,
                token_count INTEGER NOT NULL,
                embedding_model TEXT,
                embedding_status TEXT NOT NULL DEFAULT 'pending',
                embedding_batch_id TEXT,
                embedding_updated_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_screenshots_capture
                ON screenshots(captured_at_epoch DESC);
            CREATE INDEX IF NOT EXISTS idx_chunks_screenshot
                ON chunks(screenshot_id, chunk_index);

            CREATE TABLE IF NOT EXISTS ingest_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ingest_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                stage TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS batch_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL UNIQUE,
                model TEXT NOT NULL,
                local_request_path TEXT NOT NULL,
                local_manifest_path TEXT NOT NULL,
                local_result_path TEXT,
                remote_input_file_name TEXT,
                remote_output_file_name TEXT,
                status TEXT NOT NULL,
                chunk_count INTEGER NOT NULL,
                submitted_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                imported_at TEXT,
                error_message TEXT
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS screenshots_fts
                USING fts5(ocr_text);

            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(text);
            """
        )
        self._migrate_schema()
        self.conn.commit()

    def _migrate_schema(self) -> None:
        # This project already has users with older local databases.
        # These tiny migrations let us add new batch-embedding fields
        # without asking the user to delete their database and start over.
        self._ensure_column(
            table_name="chunks",
            column_name="embedding_model",
            ddl="ALTER TABLE chunks ADD COLUMN embedding_model TEXT",
        )
        self._ensure_column(
            table_name="chunks",
            column_name="embedding_status",
            ddl="ALTER TABLE chunks ADD COLUMN embedding_status TEXT NOT NULL DEFAULT 'pending'",
        )
        self._ensure_column(
            table_name="chunks",
            column_name="embedding_batch_id",
            ddl="ALTER TABLE chunks ADD COLUMN embedding_batch_id TEXT",
        )
        self._ensure_column(
            table_name="chunks",
            column_name="embedding_updated_at",
            ddl="ALTER TABLE chunks ADD COLUMN embedding_updated_at TEXT",
        )
        self.conn.execute(
            """
            UPDATE chunks
            SET
                embedding_model = COALESCE(embedding_model, ?),
                embedding_status = CASE
                    WHEN embedding IS NOT NULL THEN 'ready'
                    ELSE COALESCE(embedding_status, 'pending')
                END,
                embedding_updated_at = COALESCE(embedding_updated_at, ?)
            WHERE embedding_model IS NULL
               OR embedding_status IS NULL
               OR embedding_updated_at IS NULL
            """,
            (
                self.config.gemini_embedding_model,
                datetime.now().isoformat(),
            ),
        )

    def _ensure_column(self, table_name: str, column_name: str, ddl: str) -> None:
        existing_columns = {
            str(row["name"])
            for row in self.conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in existing_columns:
            self.conn.execute(ddl)

    def has_vector_table(self) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunk_vec'"
        ).fetchone()
        return row is not None

    def ensure_vector_table(self, dimensions: int) -> None:
        # sqlite-vec needs to know the vector length when the virtual table is created.
        if not self.vec_enabled:
            return

        if self.has_vector_table():
            stored_dimensions = self.get_state("chunk_vec_dimensions")
            if stored_dimensions and int(stored_dimensions) != dimensions:
                # Different embedding models can use different vector lengths.
                # Rather than corrupting the index or crashing inserts,
                # we fall back to the Python similarity path for this database.
                self.vec_enabled = False
            return

        self.conn.execute(
            f"CREATE VIRTUAL TABLE chunk_vec USING vec0(embedding float[{dimensions}])"
        )
        self.record_state("chunk_vec_dimensions", str(dimensions))
        self.conn.commit()

    def get_screenshot_by_path(self, file_path: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM screenshots WHERE file_path = ?",
            (file_path,),
        ).fetchone()

    def upsert_screenshot(self, record: dict[str, Any]) -> int:
        # We use an UPSERT so re-indexing a changed screenshot replaces its old OCR data cleanly.
        row = self.conn.execute(
            """
            INSERT INTO screenshots (
                file_path, captured_at_epoch, captured_at_local_iso,
                year, month, day, hour, width, height, file_size,
                sha256, source_mtime_ns, ocr_text, ocr_confidence_avg, indexed_at
            )
            VALUES (
                :file_path, :captured_at_epoch, :captured_at_local_iso,
                :year, :month, :day, :hour, :width, :height, :file_size,
                :sha256, :source_mtime_ns, :ocr_text, :ocr_confidence_avg, :indexed_at
            )
            ON CONFLICT(file_path) DO UPDATE SET
                captured_at_epoch=excluded.captured_at_epoch,
                captured_at_local_iso=excluded.captured_at_local_iso,
                year=excluded.year,
                month=excluded.month,
                day=excluded.day,
                hour=excluded.hour,
                width=excluded.width,
                height=excluded.height,
                file_size=excluded.file_size,
                sha256=excluded.sha256,
                source_mtime_ns=excluded.source_mtime_ns,
                ocr_text=excluded.ocr_text,
                ocr_confidence_avg=excluded.ocr_confidence_avg,
                indexed_at=excluded.indexed_at
            RETURNING id
            """,
            record,
        ).fetchone()
        assert row is not None
        return int(row["id"])

    def replace_chunks(self, screenshot_id: int, chunks: list[dict[str, Any]]) -> None:
        # Replacing chunks this way avoids stale text or stale embeddings after a re-index.
        old_chunk_ids = [
            int(row["id"])
            for row in self.conn.execute(
                "SELECT id FROM chunks WHERE screenshot_id = ?",
                (screenshot_id,),
            ).fetchall()
        ]
        self.conn.execute(
            "DELETE FROM chunks WHERE screenshot_id = ?",
            (screenshot_id,),
        )

        for chunk_id in old_chunk_ids:
            self.conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (chunk_id,))
            if self.vec_enabled and self.has_vector_table():
                self.conn.execute("DELETE FROM chunk_vec WHERE rowid = ?", (chunk_id,))

        for chunk in chunks:
            # Older callers and tests may only provide the original fields.
            # We fill in sane defaults here so the database layer stays backward compatible.
            chunk.setdefault("embedding_model", self.config.gemini_embedding_model)
            if chunk.get("embedding") is not None:
                chunk.setdefault("embedding_status", "ready")
            else:
                chunk.setdefault("embedding_status", "pending")
            chunk.setdefault("embedding_batch_id", None)
            chunk.setdefault("embedding_updated_at", datetime.now().isoformat())
            row = self.conn.execute(
                """
                INSERT INTO chunks (
                    screenshot_id, chunk_index, text, start_offset,
                    end_offset, embedding, token_count, embedding_model,
                    embedding_status, embedding_batch_id, embedding_updated_at
                )
                VALUES (
                    :screenshot_id, :chunk_index, :text, :start_offset,
                    :end_offset, :embedding, :token_count, :embedding_model,
                    :embedding_status, :embedding_batch_id, :embedding_updated_at
                )
                RETURNING id
                """,
                chunk,
            ).fetchone()
            assert row is not None
            chunk_row_id = int(row["id"])
            self.conn.execute(
                "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                (chunk_row_id, chunk["text"]),
            )

            if (
                self.vec_enabled
                and self.has_vector_table()
                and chunk["embedding"] is not None
            ):
                self.conn.execute(
                    "INSERT OR REPLACE INTO chunk_vec(rowid, embedding) VALUES (?, ?)",
                    (chunk_row_id, chunk["embedding"]),
                )

        self.conn.execute(
            "INSERT OR REPLACE INTO screenshots_fts(rowid, ocr_text) VALUES (?, ?)",
            (
                screenshot_id,
                self.conn.execute(
                    "SELECT ocr_text FROM screenshots WHERE id = ?",
                    (screenshot_id,),
                ).fetchone()["ocr_text"],
            ),
        )

    def record_state(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO ingest_state(key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    def get_state(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM ingest_state WHERE key = ?",
            (key,),
        ).fetchone()
        return None if row is None else str(row["value"])

    def record_error(self, file_path: str, stage: str, message: str, created_at: str) -> None:
        self.conn.execute(
            """
            INSERT INTO ingest_errors(file_path, stage, message, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (file_path, stage, message, created_at),
        )
        self.conn.commit()

    def commit(self) -> None:
        self.conn.commit()

    def status(self) -> dict[str, Any]:
        # This powers the `screenmemory status` command and the menu bar status panel.
        screenshot_count = self.conn.execute(
            "SELECT COUNT(*) AS count FROM screenshots"
        ).fetchone()["count"]
        chunk_count = self.conn.execute(
            "SELECT COUNT(*) AS count FROM chunks"
        ).fetchone()["count"]
        pending_embedding_count = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM chunks
            WHERE embedding_status = 'pending'
              AND embedding_model = ?
            """,
            (self.config.gemini_embedding_model,),
        ).fetchone()["count"]
        open_batch_job_count = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM batch_jobs
            WHERE status NOT IN ('job_succeeded_imported', 'job_failed', 'job_cancelled')
            """
        ).fetchone()["count"]
        last_scan = self.get_state("last_successful_scan_at")
        last_indexed_path = self.get_state("last_indexed_path")
        return {
            "database_path": str(self.config.database_path),
            "screenshot_count": int(screenshot_count),
            "chunk_count": int(chunk_count),
            "pending_embedding_count": int(pending_embedding_count),
            "open_batch_job_count": int(open_batch_job_count),
            "vec_enabled": self.vec_enabled,
            "last_successful_scan_at": last_scan,
            "last_indexed_path": last_indexed_path,
            "full_index_last_cursor_epoch": self.get_state("full_index_last_cursor_epoch"),
            "full_index_last_cursor_path": self.get_state("full_index_last_cursor_path"),
            "full_index_completed_at": self.get_state("full_index_completed_at"),
        }

    def search_fts_chunks(
        self,
        fts_query: str,
        start_epoch: int | None,
        end_epoch: int | None,
        limit: int,
    ) -> list[sqlite3.Row]:
        sql = """
            SELECT
                c.id AS chunk_id,
                c.screenshot_id,
                c.text,
                s.file_path,
                s.captured_at_epoch,
                s.captured_at_local_iso,
                s.ocr_text,
                bm25(chunks_fts) AS lexical_score
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN screenshots s ON s.id = c.screenshot_id
            WHERE chunks_fts MATCH ?
        """
        params: list[Any] = [fts_query]
        if start_epoch is not None:
            sql += " AND s.captured_at_epoch >= ?"
            params.append(start_epoch)
        if end_epoch is not None:
            sql += " AND s.captured_at_epoch <= ?"
            params.append(end_epoch)
        sql += " ORDER BY lexical_score LIMIT ?"
        params.append(limit)
        return self.conn.execute(sql, params).fetchall()

    def load_chunk_rows(self, chunk_ids: list[int]) -> list[sqlite3.Row]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        return self.conn.execute(
            f"""
            SELECT
                c.id AS chunk_id,
                c.screenshot_id,
                c.text,
                c.embedding,
                c.embedding_model,
                c.embedding_status,
                s.file_path,
                s.captured_at_epoch,
                s.captured_at_local_iso,
                s.ocr_text
            FROM chunks c
            JOIN screenshots s ON s.id = c.screenshot_id
            WHERE c.id IN ({placeholders})
            """,
            chunk_ids,
        ).fetchall()

    def fetch_embeddings_for_filtered_chunks(
        self,
        start_epoch: int | None,
        end_epoch: int | None,
        limit: int = 5000,
    ) -> list[sqlite3.Row]:
        # The fallback path samples the newest matching chunks if sqlite-vec is unavailable.
        sql = """
            SELECT
                c.id AS chunk_id,
                c.screenshot_id,
                c.text,
                c.embedding,
                s.file_path,
                s.captured_at_epoch,
                s.captured_at_local_iso,
                s.ocr_text
            FROM chunks c
            JOIN screenshots s ON s.id = c.screenshot_id
            WHERE c.embedding IS NOT NULL
              AND c.embedding_status = 'ready'
              AND c.embedding_model = ?
        """
        params: list[Any] = [self.config.gemini_embedding_model]
        if start_epoch is not None:
            sql += " AND s.captured_at_epoch >= ?"
            params.append(start_epoch)
        if end_epoch is not None:
            sql += " AND s.captured_at_epoch <= ?"
            params.append(end_epoch)
        sql += " ORDER BY s.captured_at_epoch DESC LIMIT ?"
        params.append(limit)
        return self.conn.execute(sql, params).fetchall()

    def vec_search(self, embedding_blob: bytes, limit: int) -> list[sqlite3.Row]:
        if not self.vec_enabled or not self.has_vector_table():
            return []
        return self.conn.execute(
            """
            SELECT
                chunk_vec.rowid AS chunk_id,
                chunk_vec.distance
            FROM chunk_vec
            JOIN chunks c ON c.id = chunk_vec.rowid
            WHERE chunk_vec.embedding MATCH ?
              AND k = ?
              AND c.embedding_status = 'ready'
              AND c.embedding_model = ?
            ORDER BY distance
            """,
            (embedding_blob, limit, self.config.gemini_embedding_model),
        ).fetchall()

    def fetch_pending_chunks_for_batch(self, limit: int) -> list[sqlite3.Row]:
        # Batch submission needs a stable ordered list so the response lines
        # can be mapped back to the same chunk ids later.
        return self.conn.execute(
            """
            SELECT
                c.id,
                c.text,
                c.embedding_model,
                s.file_path,
                s.captured_at_local_iso
            FROM chunks c
            JOIN screenshots s ON s.id = c.screenshot_id
            WHERE c.embedding_status = 'pending'
              AND c.embedding_model = ?
            ORDER BY s.captured_at_epoch ASC, c.id ASC
            LIMIT ?
            """,
            (self.config.gemini_embedding_model, limit),
        ).fetchall()

    def mark_chunks_submitted(self, chunk_ids: list[int], batch_id: str, updated_at: str) -> None:
        if not chunk_ids:
            return
        placeholders = ",".join("?" for _ in chunk_ids)
        self.conn.execute(
            f"""
            UPDATE chunks
            SET embedding_status = 'submitted',
                embedding_batch_id = ?,
                embedding_updated_at = ?
            WHERE id IN ({placeholders})
            """,
            [batch_id, updated_at, *chunk_ids],
        )
        self.conn.commit()

    def mark_chunks_failed(self, chunk_ids: list[int], batch_id: str, updated_at: str) -> None:
        if not chunk_ids:
            return
        placeholders = ",".join("?" for _ in chunk_ids)
        self.conn.execute(
            f"""
            UPDATE chunks
            SET embedding_status = 'failed',
                embedding_batch_id = ?,
                embedding_updated_at = ?
            WHERE id IN ({placeholders})
            """,
            [batch_id, updated_at, *chunk_ids],
        )
        self.conn.commit()

    def requeue_chunks_for_batch(self, batch_id: str, updated_at: str) -> int:
        # Cancelled jobs should not permanently strand their chunks.
        # Re-queueing them lets the user submit a fresh batch later.
        cursor = self.conn.execute(
            """
            UPDATE chunks
            SET embedding_status = 'pending',
                embedding_batch_id = NULL,
                embedding_updated_at = ?,
                embedding = NULL
            WHERE embedding_batch_id = ?
              AND embedding_status IN ('submitted', 'failed')
            """,
            (updated_at, batch_id),
        )
        self.conn.commit()
        return int(cursor.rowcount)

    def cancel_chunks_for_batch(self, batch_id: str, updated_at: str) -> int:
        # This helper is the "stop and do not resume" version of re-queueing.
        # We use it when the user explicitly says they want to cancel work,
        # not postpone it for later.
        #
        # In plain English:
        # - any chunk already tied to this remote batch job
        # - and still waiting on batch results
        # becomes locally "cancelled"
        #
        # That keeps `status` honest because these chunks are no longer pending,
        # and they should not look like active submitted work either.
        cursor = self.conn.execute(
            """
            UPDATE chunks
            SET embedding = NULL,
                embedding_status = 'cancelled',
                embedding_batch_id = NULL,
                embedding_updated_at = ?
            WHERE embedding_batch_id = ?
              AND embedding_status IN ('submitted', 'failed')
            """,
            (updated_at, batch_id),
        )
        self.conn.commit()
        return int(cursor.rowcount)

    def clear_pending_embeddings(self, updated_at: str) -> int:
        # These are chunks that were only queued locally and never shipped to Gemini.
        # Clearing them is the "panic button" behavior the user asked for:
        # the queue should drop to zero instead of sitting there waiting forever.
        cursor = self.conn.execute(
            """
            UPDATE chunks
            SET embedding = NULL,
                embedding_status = 'cancelled',
                embedding_batch_id = NULL,
                embedding_updated_at = ?
            WHERE embedding_status = 'pending'
              AND embedding_model = ?
            """,
            (updated_at, self.config.gemini_embedding_model),
        )
        self.conn.commit()
        return int(cursor.rowcount)

    def record_batch_job(self, record: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO batch_jobs (
                batch_id, model, local_request_path, local_manifest_path, local_result_path,
                remote_input_file_name, remote_output_file_name, status, chunk_count,
                submitted_at, updated_at, imported_at, error_message
            )
            VALUES (
                :batch_id, :model, :local_request_path, :local_manifest_path, :local_result_path,
                :remote_input_file_name, :remote_output_file_name, :status, :chunk_count,
                :submitted_at, :updated_at, :imported_at, :error_message
            )
            """,
            record,
        )
        self.conn.commit()

    def get_batch_job(self, batch_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM batch_jobs WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()

    def list_batch_jobs(self, only_open: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM batch_jobs"
        if only_open:
            sql += " WHERE status NOT IN ('job_succeeded_imported', 'job_failed', 'job_cancelled')"
        sql += " ORDER BY submitted_at DESC"
        return self.conn.execute(sql).fetchall()

    def update_batch_job(
        self,
        batch_id: str,
        *,
        status: str,
        updated_at: str,
        remote_output_file_name: str | None = None,
        local_result_path: str | None = None,
        imported_at: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE batch_jobs
            SET status = ?,
                updated_at = ?,
                remote_output_file_name = COALESCE(?, remote_output_file_name),
                local_result_path = COALESCE(?, local_result_path),
                imported_at = COALESCE(?, imported_at),
                error_message = ?
            WHERE batch_id = ?
            """,
            (
                status,
                updated_at,
                remote_output_file_name,
                local_result_path,
                imported_at,
                error_message,
                batch_id,
            ),
        )
        self.conn.commit()

    def apply_batch_embeddings(
        self,
        *,
        chunk_ids: list[int],
        embeddings: list[list[float] | None],
        batch_id: str,
        embedding_model: str,
        updated_at: str,
    ) -> dict[str, int]:
        # The batch output comes back in the same order as the request file.
        # That makes it safe to zip the result lines back to the original chunk ids.
        ready_count = 0
        failed_count = 0
        dimensions: int | None = None

        for chunk_id, embedding in zip(chunk_ids, embeddings):
            if embedding is None:
                self.conn.execute(
                    """
                    UPDATE chunks
                    SET embedding = NULL,
                        embedding_model = ?,
                        embedding_status = 'failed',
                        embedding_batch_id = ?,
                        embedding_updated_at = ?
                    WHERE id = ?
                    """,
                    (embedding_model, batch_id, updated_at, chunk_id),
                )
                failed_count += 1
                continue

            if dimensions is None:
                dimensions = len(embedding)

            embedding_blob = serialize_embedding(embedding)
            self.conn.execute(
                """
                UPDATE chunks
                SET embedding = ?,
                    embedding_model = ?,
                    embedding_status = 'ready',
                    embedding_batch_id = ?,
                    embedding_updated_at = ?
                WHERE id = ?
                """,
                (embedding_blob, embedding_model, batch_id, updated_at, chunk_id),
            )
            ready_count += 1

        if dimensions:
            self.ensure_vector_table(dimensions)

        if self.vec_enabled and self.has_vector_table():
            placeholders = ",".join("?" for _ in chunk_ids)
            rows = self.conn.execute(
                f"""
                SELECT id, embedding, embedding_status
                FROM chunks
                WHERE id IN ({placeholders})
                """,
                chunk_ids,
            ).fetchall()
            for row in rows:
                self.conn.execute("DELETE FROM chunk_vec WHERE rowid = ?", (int(row["id"]),))
                if row["embedding"] is not None and row["embedding_status"] == "ready":
                    self.conn.execute(
                        "INSERT OR REPLACE INTO chunk_vec(rowid, embedding) VALUES (?, ?)",
                        (int(row["id"]), row["embedding"]),
                    )

        self.conn.commit()
        return {"ready": ready_count, "failed": failed_count}
