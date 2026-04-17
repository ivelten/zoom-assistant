"""Tests for zoom_assistant.image."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from zoom_assistant.image import guess_mime_type, stitch_vertical


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


def _make_image(path: Path, *, size: tuple[int, int], color: tuple[int, int, int]) -> Path:
    Image.new("RGB", size, color=color).save(path)
    return path


class TestStitchVertical:
    def test_empty_list_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            stitch_vertical([])

    def test_single_image_round_trips(self, tmp_path: Path) -> None:
        path = _make_image(tmp_path / "a.png", size=(50, 60), color=(255, 0, 0))
        stitched = stitch_vertical([path])
        result = Image.open(BytesIO(stitched))
        assert result.size == (50, 60)

    def test_two_images_stack_vertically(self, tmp_path: Path) -> None:
        a = _make_image(tmp_path / "a.png", size=(40, 30), color=(255, 0, 0))
        b = _make_image(tmp_path / "b.png", size=(40, 50), color=(0, 0, 255))
        stitched = stitch_vertical([a, b])
        result = Image.open(BytesIO(stitched))
        assert result.size == (40, 80)

    def test_widest_wins_narrower_centered_with_white_padding(self, tmp_path: Path) -> None:
        wide = _make_image(tmp_path / "wide.png", size=(100, 10), color=(255, 0, 0))
        narrow = _make_image(tmp_path / "narrow.png", size=(40, 10), color=(0, 255, 0))
        stitched = stitch_vertical([wide, narrow])
        result = Image.open(BytesIO(stitched))
        assert result.size == (100, 20)
        # Padding pixel at the start of the narrow row should be white.
        assert result.convert("RGB").getpixel((0, 15)) == (255, 255, 255)
