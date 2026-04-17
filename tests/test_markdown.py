"""Tests for zoom_assistant.markdown."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from zoom_assistant.markdown import (
    FigureLink,
    Heading,
    ImageNote,
    Section,
    render_image_note,
)


def _fixed_time() -> datetime:
    return datetime(2026, 4, 17, 14, 32, 0, tzinfo=UTC)


class TestHeading:
    def test_lower_bound(self) -> None:
        Heading(2, "ok")

    def test_upper_bound(self) -> None:
        Heading(6, "ok")

    def test_too_shallow_rejects(self) -> None:
        with pytest.raises(ValueError, match="heading level"):
            Heading(1, "top")

    def test_too_deep_rejects(self) -> None:
        with pytest.raises(ValueError, match="heading level"):
            Heading(7, "bottom")


def test_timezone_aware_required() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ImageNote(
            filename="a.png",
            taken_at=datetime(2026, 1, 1, 12, 0),
            sections=(),
            figures=(),
        )


def test_minimal_note_renders_header_only() -> None:
    note = ImageNote(
        filename="IMG.png",
        taken_at=_fixed_time(),
        sections=(),
        figures=(),
    )
    output = render_image_note(note)
    assert output == "---\n\n# IMG.png\n\n*2026-04-17T14:32:00+00:00*\n\n"


def test_full_note_renders_sections_and_figures() -> None:
    note = ImageNote(
        filename="IMG.png",
        taken_at=_fixed_time(),
        sections=(
            Section(heading=Heading(2, "Intro"), body="Body here."),
            Section(heading=Heading(3, "Detail"), body="More text."),
        ),
        figures=(FigureLink(caption="Diagram", relative_path="assets/IMG-crop-1.png"),),
    )
    output = render_image_note(note)
    assert output.startswith("---\n\n# IMG.png\n\n*2026-04-17T14:32:00+00:00*\n\n")
    assert "## Intro\n\nBody here." in output
    assert "### Detail\n\nMore text." in output
    assert "![Diagram](assets/IMG-crop-1.png)" in output
    assert output.endswith("\n\n")


def test_section_with_heading_no_body() -> None:
    note = ImageNote(
        filename="a.png",
        taken_at=_fixed_time(),
        sections=(Section(heading=Heading(2, "Only heading"), body=""),),
        figures=(),
    )
    output = render_image_note(note)
    assert "## Only heading" in output


def test_section_with_body_no_heading() -> None:
    note = ImageNote(
        filename="a.png",
        taken_at=_fixed_time(),
        sections=(Section(heading=None, body="just prose"),),
        figures=(),
    )
    output = render_image_note(note)
    assert "just prose" in output
    assert "## " not in output


def test_empty_section_dropped_without_extra_blank_lines() -> None:
    note = ImageNote(
        filename="a.png",
        taken_at=_fixed_time(),
        sections=(Section(heading=None, body="   "),),
        figures=(),
    )
    output = render_image_note(note)
    assert "\n\n\n" not in output


def test_two_renders_concatenate_with_blank_line_between() -> None:
    first = render_image_note(
        ImageNote(filename="1.png", taken_at=_fixed_time(), sections=(), figures=())
    )
    second = render_image_note(
        ImageNote(filename="2.png", taken_at=_fixed_time(), sections=(), figures=())
    )
    combined = first + second
    assert "\n\n---\n\n# 2.png" in combined
