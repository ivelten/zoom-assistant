"""Image-I/O helpers: MIME detection for notes-ocr source images."""

from __future__ import annotations

from pathlib import Path

_JPEG_SUFFIXES = frozenset({".jpg", ".jpeg"})


def guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in _JPEG_SUFFIXES:
        return "image/jpeg"
    raise ValueError(f"unsupported image extension: {path.suffix!r}")
