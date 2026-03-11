from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ScreenMemoryConfig:
    # This folder is the user's real screenshot source tree.
    screenshot_root: Path
    # Everything we generate must go under app support, never under the screenshot tree.
    app_support_dir: Path
    database_path: Path
    thumbnail_cache_dir: Path
    log_dir: Path
    batch_dir: Path
    batch_requests_dir: Path
    batch_results_dir: Path
    launch_agent_path: Path
    full_index_launch_agent_path: Path
    gemini_api_key: str | None
    gemini_generation_model: str
    gemini_embedding_model: str
    timezone_name: str
    thumbnail_size: int
    default_recent_days: int
    default_query_limit: int


def load_config() -> ScreenMemoryConfig:
    # We use explicit absolute defaults so the project works right away on this machine.
    # We also read a local `.env` file first so the user does not need to export keys every session.
    _load_local_dotenv(Path.cwd() / ".env")

    home = Path.home()
    app_support_dir = home / "Library" / "Application Support" / "ScreenMemoryRAG"
    batch_dir = app_support_dir / "batch"
    launch_agents_dir = home / "Library" / "LaunchAgents"
    gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    return ScreenMemoryConfig(
        screenshot_root=Path(
            os.getenv(
                "SCREENMEMORY_SCREENSHOT_ROOT",
                "/Users/alanman/ScreenMemoryData/screenshots",
            )
        ).expanduser(),
        app_support_dir=Path(
            os.getenv("SCREENMEMORY_APP_SUPPORT", str(app_support_dir))
        ).expanduser(),
        database_path=Path(
            os.getenv(
                "SCREENMEMORY_DATABASE_PATH",
                str(app_support_dir / "screenmemory.db"),
            )
        ).expanduser(),
        thumbnail_cache_dir=Path(
            os.getenv(
                "SCREENMEMORY_THUMBNAIL_CACHE",
                str(app_support_dir / "thumbnails"),
            )
        ).expanduser(),
        log_dir=Path(
            os.getenv("SCREENMEMORY_LOG_DIR", str(app_support_dir / "logs"))
        ).expanduser(),
        batch_dir=Path(
            os.getenv("SCREENMEMORY_BATCH_DIR", str(batch_dir))
        ).expanduser(),
        batch_requests_dir=Path(
            os.getenv(
                "SCREENMEMORY_BATCH_REQUESTS_DIR",
                str(batch_dir / "requests"),
            )
        ).expanduser(),
        batch_results_dir=Path(
            os.getenv(
                "SCREENMEMORY_BATCH_RESULTS_DIR",
                str(batch_dir / "results"),
            )
        ).expanduser(),
        launch_agent_path=Path(
            os.getenv(
                "SCREENMEMORY_LAUNCH_AGENT_PATH",
                str(launch_agents_dir / "io.alanman.screenmemoryrag.plist"),
            )
        ).expanduser(),
        full_index_launch_agent_path=Path(
            os.getenv(
                "SCREENMEMORY_FULL_INDEX_LAUNCH_AGENT_PATH",
                str(launch_agents_dir / "io.alanman.screenmemoryrag.fullindex.plist"),
            )
        ).expanduser(),
        gemini_api_key=gemini_api_key,
        gemini_generation_model=os.getenv(
            "SCREENMEMORY_GEMINI_MODEL",
            "gemini-2.5-flash",
        ),
        gemini_embedding_model=os.getenv(
            "SCREENMEMORY_GEMINI_EMBED_MODEL",
            "gemini-embedding-001",
        ),
        timezone_name=os.getenv("TZ", "America/Los_Angeles"),
        thumbnail_size=int(os.getenv("SCREENMEMORY_THUMBNAIL_SIZE", "320")),
        default_recent_days=int(os.getenv("SCREENMEMORY_RECENT_DAYS", "14")),
        default_query_limit=int(os.getenv("SCREENMEMORY_QUERY_LIMIT", "8")),
    )


def _load_local_dotenv(dotenv_path: Path) -> None:
    # This tiny loader keeps the project dependency-light.
    # For this project, the repo-local `.env` should win so the app uses the intended key.
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ[key] = value
