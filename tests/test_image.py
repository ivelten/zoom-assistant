"""Tests for zoom_assistant.image."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from zoom_assistant.image import (
    NormalizedBox,
    crop_normalized,
    encode_png,
    guess_mime_type,
    write_png,
)


def _red_square(size: int = 100) -> Image.Image:
    return Image.new("RGB", (size, size), color=(255, 0, 0))


class TestNormalizedBox:
    def test_full_image_box(self) -> None:
        box = NormalizedBox(0.0, 0.0, 1.0, 1.0)
        assert box.x0 == 0.0
        assert box.x1 == 1.0

    def test_coordinate_below_zero_rejects(self) -> None:
        with pytest.raises(ValueError, match="x0"):
            NormalizedBox(-0.1, 0.0, 1.0, 1.0)

    def test_coordinate_above_one_rejects(self) -> None:
        with pytest.raises(ValueError, match="y1"):
            NormalizedBox(0.0, 0.0, 1.0, 1.5)

    def test_degenerate_x_range_rejects(self) -> None:
        with pytest.raises(ValueError, match="x1"):
            NormalizedBox(0.5, 0.0, 0.5, 1.0)

    def test_degenerate_y_range_rejects(self) -> None:
        with pytest.raises(ValueError, match="y1"):
            NormalizedBox(0.0, 0.5, 1.0, 0.5)


def test_crop_normalized_returns_expected_size() -> None:
    image = _red_square(100)
    box = NormalizedBox(0.0, 0.0, 0.5, 0.5)
    cropped = crop_normalized(image, box)
    assert cropped.size == (50, 50)


def test_crop_normalized_offset_region() -> None:
    image = _red_square(200)
    box = NormalizedBox(0.25, 0.25, 0.75, 0.75)
    cropped = crop_normalized(image, box)
    assert cropped.size == (100, 100)


def test_encode_png_round_trips() -> None:
    image = _red_square(10)
    png_bytes = encode_png(image)
    assert png_bytes.startswith(b"\x89PNG")
    roundtrip = Image.open(BytesIO(png_bytes))
    assert roundtrip.size == (10, 10)


def test_write_png_creates_parent_dirs(tmp_path: Path) -> None:
    image = _red_square(10)
    target = tmp_path / "nested" / "dir" / "out.png"
    write_png(image, target)
    assert target.exists()
    assert Image.open(target).size == (10, 10)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a.png", "image/png"),
        ("A.PNG", "image/png"),
        ("b.jpg", "image/jpeg"),
        ("c.jpeg", "image/jpeg"),
        ("d.JPEG", "image/jpeg"),
    ],
)
def test_guess_mime_type_known(name: str, expected: str) -> None:
    assert guess_mime_type(Path(name)) == expected


def test_guess_mime_type_rejects_unknown_extension() -> None:
    with pytest.raises(ValueError, match="gif"):
        guess_mime_type(Path("a.gif"))
