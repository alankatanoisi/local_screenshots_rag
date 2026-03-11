from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

from screenmemory.config import ScreenMemoryConfig


class ThumbnailManager:
    def __init__(self, config: ScreenMemoryConfig) -> None:
        # Thumbnails live in our own cache folder, never beside the screenshots.
        self.config = config

    def get_or_create(self, source_path: str) -> str:
        source = Path(source_path)
        stat = source.stat()
        cache_key = hashlib.sha1(
            f"{source.resolve()}::{stat.st_mtime_ns}::{stat.st_size}::{self.config.thumbnail_size}".encode(
                "utf-8"
            )
        ).hexdigest()
        output_path = self.config.thumbnail_cache_dir / f"{cache_key}.jpg"

        if output_path.exists():
            return str(output_path)

        # Pillow only reads the source image here; the written file goes to our separate cache directory.
        with Image.open(source) as image:
            image = image.convert("RGB")
            image.thumbnail((self.config.thumbnail_size, self.config.thumbnail_size))
            image.save(output_path, format="JPEG", quality=80, optimize=True)

        self._trim_cache(max_items=200)
        return str(output_path)

    def _trim_cache(self, max_items: int) -> None:
        # A tiny LRU-like cleanup keeps the cache small on an 8 GB machine.
        cached_files = sorted(
            self.config.thumbnail_cache_dir.glob("*.jpg"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for stale in cached_files[max_items:]:
            stale.unlink(missing_ok=True)
