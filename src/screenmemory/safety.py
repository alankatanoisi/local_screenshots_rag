from __future__ import annotations

from pathlib import Path

from screenmemory.config import ScreenMemoryConfig


def _resolved(path: Path) -> Path:
    # Resolving lets us compare real absolute paths instead of trusting user input strings.
    return path.expanduser().resolve()


def ensure_safe_storage_paths(config: ScreenMemoryConfig) -> None:
    # This is the critical safety guard:
    # no database, cache, logs, or launchd plist may live inside the screenshot source tree.
    screenshot_root = _resolved(config.screenshot_root)
    managed_paths = [
        config.app_support_dir,
        config.database_path,
        config.thumbnail_cache_dir,
        config.log_dir,
        config.batch_dir,
        config.batch_requests_dir,
        config.batch_results_dir,
        config.launch_agent_path,
        config.full_index_launch_agent_path,
    ]

    for managed_path in managed_paths:
        resolved = _resolved(managed_path)
        if screenshot_root == resolved or screenshot_root in resolved.parents:
            raise ValueError(
                "Unsafe configuration: managed data path is inside the screenshot source tree. "
                f"Refusing to continue: {resolved}"
            )


def ensure_runtime_directories(config: ScreenMemoryConfig) -> None:
    # We create only our own folders, and only after the safety guard passes.
    ensure_safe_storage_paths(config)
    config.app_support_dir.mkdir(parents=True, exist_ok=True)
    config.thumbnail_cache_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    config.batch_dir.mkdir(parents=True, exist_ok=True)
    config.batch_requests_dir.mkdir(parents=True, exist_ok=True)
    config.batch_results_dir.mkdir(parents=True, exist_ok=True)
    config.launch_agent_path.parent.mkdir(parents=True, exist_ok=True)
