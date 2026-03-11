from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from screenmemory.batch_embeddings import BatchEmbeddingClient
from screenmemory.db import Database, deserialize_embedding
from screenmemory.ingest import run_index_pass
from screenmemory.ocr import OCRResult
from screenmemory.safety import ensure_runtime_directories

from tests.helpers import make_test_image


class _FakeFilesAPI:
    def upload(self, *, file, config):
        return SimpleNamespace(name="files/input-123")

    def download(self, *, file):
        return b'{"response":{"embedding":{"values":[0.25,0.75]}}}\n'


class _FakeBatchesAPI:
    def __init__(self) -> None:
        self.cancelled_names: list[str] = []

    def create_embeddings(self, *, model, src, config):
        return SimpleNamespace(
            name="batches/123",
            state=SimpleNamespace(name="JOB_STATE_PENDING"),
            dest=None,
        )

    def cancel(self, *, name):
        self.cancelled_names.append(name)
        return SimpleNamespace(name=name)

    def get(self, *, name):
        if name in self.cancelled_names:
            return SimpleNamespace(
                name=name,
                state=SimpleNamespace(name="JOB_STATE_CANCELLED"),
                dest=None,
                error=None,
            )
        return SimpleNamespace(
            name=name,
            state=SimpleNamespace(name="JOB_STATE_SUCCEEDED"),
            dest=SimpleNamespace(file_name="files/output-123"),
            error=None,
        )


class _FakeSDKClient:
    def __init__(self) -> None:
        self.files = _FakeFilesAPI()
        self.batches = _FakeBatchesAPI()


def test_batch_indexing_queues_pending_embeddings(monkeypatch, app_paths) -> None:
    ensure_runtime_directories(app_paths)
    screenshot = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769392950.jpeg"
    make_test_image(screenshot, "batch mode")

    monkeypatch.setattr(
        "screenmemory.ingest.run_tesseract",
        lambda _path: OCRResult(text="batch mode", confidence_avg=92.0),
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
            embedding_mode="batch",
        )
        chunk_row = db.conn.execute(
            "SELECT embedding_status, embedding_model, embedding FROM chunks"
        ).fetchone()
        status = db.status()
    finally:
        db.close()

    assert summary["processed"] == 1
    assert chunk_row is not None
    assert chunk_row["embedding_status"] == "pending"
    assert chunk_row["embedding_model"] == app_paths.gemini_embedding_model
    assert chunk_row["embedding"] is None
    assert status["pending_embedding_count"] == 1


def test_batch_submit_and_sync_imports_embeddings(monkeypatch, app_paths) -> None:
    ensure_runtime_directories(app_paths)
    screenshot = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769392950.jpeg"
    make_test_image(screenshot, "batch import")

    monkeypatch.setattr(
        "screenmemory.ingest.run_tesseract",
        lambda _path: OCRResult(text="batch import", confidence_avg=92.0),
    )

    batch_client = BatchEmbeddingClient(app_paths)
    batch_client._sdk_client = _FakeSDKClient()

    db = Database(app_paths)
    try:
        run_index_pass(
            config=app_paths,
            db=db,
            gemini=None,
            recent_days=None,
            batch_limit=None,
            mode="recent",
            embedding_mode="batch",
        )
        submit_summary = batch_client.submit_pending_embeddings(db=db, limit=10)
        sync_summary = batch_client.sync_batch_jobs(db=db)
        chunk_row = db.conn.execute(
            "SELECT embedding_status, embedding_batch_id, embedding FROM chunks"
        ).fetchone()
        job_row = db.get_batch_job("batches/123")
    finally:
        db.close()

    assert submit_summary["submitted"] is True
    assert sync_summary["imported_ready"] == 1
    assert chunk_row is not None
    assert chunk_row["embedding_status"] == "ready"
    assert chunk_row["embedding_batch_id"] == "batches/123"
    assert deserialize_embedding(chunk_row["embedding"]) == [0.25, 0.75]
    assert job_row is not None
    assert job_row["status"] == "job_succeeded_imported"
    assert Path(job_row["local_result_path"]).exists()


def test_cancel_batches_clears_remote_and_local_queue(monkeypatch, app_paths) -> None:
    ensure_runtime_directories(app_paths)
    screenshot = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769392950.jpeg"
    make_test_image(screenshot, "cancel me")

    monkeypatch.setattr(
        "screenmemory.ingest.run_tesseract",
        lambda _path: OCRResult(text="cancel me", confidence_avg=92.0),
    )

    batch_client = BatchEmbeddingClient(app_paths)
    fake_sdk = _FakeSDKClient()
    batch_client._sdk_client = fake_sdk

    db = Database(app_paths)
    try:
        run_index_pass(
            config=app_paths,
            db=db,
            gemini=None,
            recent_days=None,
            batch_limit=None,
            mode="recent",
            embedding_mode="batch",
        )
        submit_summary = batch_client.submit_pending_embeddings(db=db, limit=10)
        cancel_summary = batch_client.cancel_batch_jobs(db=db, batch_id=None, clear_pending=True)
        chunk_row = db.conn.execute(
            "SELECT embedding_status, embedding_batch_id, embedding FROM chunks"
        ).fetchone()
        job_row = db.get_batch_job("batches/123")
        status = db.status()
    finally:
        db.close()

    assert submit_summary["submitted"] is True
    assert cancel_summary["jobs_requested"] == 1
    assert cancel_summary["jobs_closed"] == 1
    assert cancel_summary["submitted_chunks_cleared"] == 1
    assert cancel_summary["pending_chunks_cleared"] == 0
    assert fake_sdk.batches.cancelled_names == ["batches/123"]
    assert chunk_row is not None
    assert chunk_row["embedding_status"] == "cancelled"
    assert chunk_row["embedding_batch_id"] is None
    assert chunk_row["embedding"] is None
    assert job_row is not None
    assert job_row["status"] == "job_cancelled"
    assert status["pending_embedding_count"] == 0
    assert status["open_batch_job_count"] == 0


def test_cancel_batches_can_clear_never_submitted_pending_chunks(monkeypatch, app_paths) -> None:
    ensure_runtime_directories(app_paths)
    screenshot = app_paths.screenshot_root / "2026" / "01" / "25" / "18" / "1769392950.jpeg"
    make_test_image(screenshot, "pending only")

    monkeypatch.setattr(
        "screenmemory.ingest.run_tesseract",
        lambda _path: OCRResult(text="pending only", confidence_avg=92.0),
    )

    batch_client = BatchEmbeddingClient(app_paths)
    batch_client._sdk_client = _FakeSDKClient()

    db = Database(app_paths)
    try:
        run_index_pass(
            config=app_paths,
            db=db,
            gemini=None,
            recent_days=None,
            batch_limit=None,
            mode="recent",
            embedding_mode="batch",
        )
        cancel_summary = batch_client.cancel_batch_jobs(db=db, batch_id=None, clear_pending=True)
        chunk_row = db.conn.execute(
            "SELECT embedding_status, embedding_batch_id, embedding FROM chunks"
        ).fetchone()
        status = db.status()
    finally:
        db.close()

    assert cancel_summary["jobs_requested"] == 0
    assert cancel_summary["pending_chunks_cleared"] == 1
    assert chunk_row is not None
    assert chunk_row["embedding_status"] == "cancelled"
    assert chunk_row["embedding_batch_id"] is None
    assert chunk_row["embedding"] is None
    assert status["pending_embedding_count"] == 0
