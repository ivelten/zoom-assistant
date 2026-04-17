"""Markdown emitter for per-folder notes-ocr output.

`render_folder_note` produces the full text body of a `<folder-name>.md`
file: a single `# <folder name>` heading followed by the OCR sections
returned by Gemini.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass


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
class FolderNote:
    title: str
    sections: Sequence[Section]


def render_folder_note(note: FolderNote) -> str:
    blocks = [f"# {note.title}", *_render_sections(note.sections)]
    return "\n\n".join(block for block in blocks if block) + "\n"


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
