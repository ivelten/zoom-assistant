"""Pillow-based image I/O for notes-ocr: decode, crop with normalized boxes, encode PNG."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image

_JPEG_SUFFIXES = frozenset({".jpg", ".jpeg"})


@dataclass(frozen=True, slots=True)
class NormalizedBox:
    """Axis-aligned bounding box with coordinates in [0, 1].

    Coordinates are inclusive at the min corner and exclusive at the max
    corner, matching Pillow's `Image.crop` convention after scaling.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        _validate_unit_interval("x0", self.x0)
        _validate_unit_interval("y0", self.y0)
        _validate_unit_interval("x1", self.x1)
        _validate_unit_interval("y1", self.y1)
        if self.x1 <= self.x0:
            raise ValueError(f"x1 ({self.x1}) must exceed x0 ({self.x0})")
        if self.y1 <= self.y0:
            raise ValueError(f"y1 ({self.y1}) must exceed y0 ({self.y0})")


def load_image(path: Path) -> Image.Image:
    return Image.open(path)


def crop_normalized(image: Image.Image, box: NormalizedBox) -> Image.Image:
    width, height = image.size
    pixel_box = (
        int(box.x0 * width),
        int(box.y0 * height),
        int(box.x1 * width),
        int(box.y1 * height),
    )
    return image.crop(pixel_box)


def encode_png(image: Image.Image) -> bytes:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def write_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in _JPEG_SUFFIXES:
        return "image/jpeg"
    raise ValueError(f"unsupported image extension: {path.suffix!r}")


def _validate_unit_interval(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")
