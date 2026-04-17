"""Tests for zoom_assistant.markdown."""

from __future__ import annotations

import pytest

from zoom_assistant.markdown import FolderNote, Heading, Section, render_folder_note


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


def test_minimal_note_renders_only_title() -> None:
    note = FolderNote(title="Aula 04", sections=())
    assert render_folder_note(note) == "# Aula 04\n"


def test_full_note_renders_sections_under_title() -> None:
    note = FolderNote(
        title="Aula 04",
        sections=(
            Section(heading=Heading(2, "Intro"), body="Body here."),
            Section(heading=Heading(3, "Detail"), body="More text."),
        ),
    )
    output = render_folder_note(note)
    assert output.startswith("# Aula 04\n\n")
    assert "## Intro\n\nBody here." in output
    assert "### Detail\n\nMore text." in output
    assert output.endswith("\n")


def test_section_with_heading_no_body() -> None:
    note = FolderNote(
        title="X",
        sections=(Section(heading=Heading(2, "Only heading"), body=""),),
    )
    output = render_folder_note(note)
    assert "## Only heading" in output


def test_section_with_body_no_heading() -> None:
    note = FolderNote(
        title="X",
        sections=(Section(heading=None, body="just prose"),),
    )
    output = render_folder_note(note)
    assert "just prose" in output
    assert "## " not in output


def test_empty_section_dropped_without_extra_blank_lines() -> None:
    note = FolderNote(
        title="X",
        sections=(Section(heading=None, body="   "),),
    )
    output = render_folder_note(note)
    assert "\n\n\n" not in output
