"""Image-I/O helpers for notes-ocr: MIME detection and vertical stitching."""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from pathlib import Path

from PIL import Image

_JPEG_SUFFIXES = frozenset({".jpg", ".jpeg"})
_STITCH_BACKGROUND = (255, 255, 255)


def guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in _JPEG_SUFFIXES:
        return "image/jpeg"
    raise ValueError(f"unsupported image extension: {path.suffix!r}")


def stitch_vertical(paths: Sequence[Path]) -> bytes:
    """Stack images top-to-bottom in `paths` order; return PNG bytes.

    Images narrower than the widest are centered horizontally on a white
    background. Used by the `--single-request` mode to merge a folder's
    screenshots into one tall PNG for a single Gemini OCR call.
    """
    if not paths:
        raise ValueError("stitch_vertical requires at least one image")
    pil_images = [Image.open(p) for p in paths]
    width = max(img.width for img in pil_images)
    total_height = sum(img.height for img in pil_images)
    canvas = Image.new("RGB", (width, total_height), color=_STITCH_BACKGROUND)
    y_offset = 0
    for img in pil_images:
        x_offset = (width - img.width) // 2
        canvas.paste(_to_rgb(img), (x_offset, y_offset))
        y_offset += img.height
    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    return image.convert("RGB")
