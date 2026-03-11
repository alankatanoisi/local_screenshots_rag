from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def make_test_image(path: Path, text: str) -> None:
    # The test images are real JPEGs so Pillow can read them like production code does.
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (600, 300), color="white")
    drawer = ImageDraw.Draw(image)
    drawer.text((20, 20), text, fill="black")
    image.save(path, format="JPEG")
