"""Markdown emitter for per-image notes-ocr sections.

Each call to `render_image_note` produces a self-contained block ending in a
blank line, safe to append to `notes.md` without extra glue.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Heading:
    level: int
    text: str

    def __post_init__(self) -> None:
        if not 2 <= self.level <= 6:
            raise ValueError(f"heading level must be 2..6, got {self.level}")


@dataclass(frozen=True, slots=True)
class Section:
    heading: Heading | None
    body: str


@dataclass(frozen=True, slots=True)
class FigureLink:
    caption: str
    relative_path: str


@dataclass(frozen=True, slots=True)
class ImageNote:
    filename: str
    taken_at: datetime
    sections: Sequence[Section]
    figures: Sequence[FigureLink]

    def __post_init__(self) -> None:
        if self.taken_at.tzinfo is None:
            raise ValueError("taken_at must be timezone-aware")


def render_image_note(note: ImageNote) -> str:
    blocks = [
        "---",
        f"# {note.filename}",
        f"*{note.taken_at.isoformat()}*",
        *_render_sections(note.sections),
        *_render_figures(note.figures),
    ]
    return "\n\n".join(block for block in blocks if block) + "\n\n"


def _render_sections(sections: Sequence[Section]) -> Iterator[str]:
    for section in sections:
        rendered = _render_section(section)
        if rendered:
            yield rendered


def _render_section(section: Section) -> str:
    parts: list[str] = []
    if section.heading is not None:
        parts.append(f"{'#' * section.heading.level} {section.heading.text}")
    body = section.body.strip()
    if body:
        parts.append(body)
    return "\n\n".join(parts)


def _render_figures(figures: Sequence[FigureLink]) -> Iterator[str]:
    for figure in figures:
        yield f"![{figure.caption}]({figure.relative_path})"
