"""Tests for zoom_assistant.image."""

from __future__ import annotations

from pathlib import Path

import pytest

from zoom_assistant.image import guess_mime_type


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
