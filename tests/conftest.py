from __future__ import annotations

from pathlib import Path

import pytest
from screenmemory.config import ScreenMemoryConfig


@pytest.fixture()
def app_paths(tmp_path: Path) -> ScreenMemoryConfig:
    # Each test gets its own isolated screenshot root and app-support folder.
    screenshot_root = tmp_path / "screenshots"
    app_support = tmp_path / "app-support"
    screenshot_root.mkdir(parents=True)
    return ScreenMemoryConfig(
        screenshot_root=screenshot_root,
        app_support_dir=app_support,
        database_path=app_support / "screenmemory.db",
        thumbnail_cache_dir=app_support / "thumbnails",
        log_dir=app_support / "logs",
        batch_dir=app_support / "batch",
        batch_requests_dir=app_support / "batch" / "requests",
        batch_results_dir=app_support / "batch" / "results",
        launch_agent_path=tmp_path / "launch-agents" / "io.alanman.screenmemoryrag.plist",
        full_index_launch_agent_path=tmp_path / "launch-agents" / "io.alanman.screenmemoryrag.fullindex.plist",
        gemini_api_key=None,
        gemini_generation_model="gemini-2.5-flash",
        gemini_embedding_model="gemini-embedding-2-preview",
        google_cloud_project=None,
        google_cloud_location=None,
        genai_use_vertexai=False,
        timezone_name="America/Los_Angeles",
        thumbnail_size=256,
        default_recent_days=14,
        default_query_limit=8,
    )
