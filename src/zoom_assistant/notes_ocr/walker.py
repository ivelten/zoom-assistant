"""Recursive walker that yields note folders with their image lists.

Per CLAUDE.md: a directory is a note folder iff it contains image files
(`.png` / `.jpg` / `.jpeg`, case-insensitive) directly. Every note folder
gets its own `notes.md` — no merging across folders. Subdirectories are
walked independently and may become note folders themselves. Hidden
entries (dot-prefixed) are filtered. Image order within a folder is
filename-sorted; sibling folders are walked in sorted name order for
deterministic discovery.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg"})


@dataclass(frozen=True, slots=True)
class NoteFolder:
    path: Path
    images: tuple[Path, ...]


def walk_note_folders(root: Path) -> Iterator[NoteFolder]:
    """Yield note folders found under `root`, in top-down discovery order."""
    yield from _walk(root)


def _walk(path: Path) -> Iterator[NoteFolder]:
    images = sorted(_list_images(path), key=lambda p: p.name)
    if images:
        yield NoteFolder(path=path, images=tuple(images))
    for subdir in sorted(_list_subdirs(path), key=lambda p: p.name):
        yield from _walk(subdir)


def _list_images(path: Path) -> list[Path]:
    return [p for p in path.iterdir() if not p.name.startswith(".") and _is_image(p)]


def _list_subdirs(path: Path) -> list[Path]:
    return [p for p in path.iterdir() if not p.name.startswith(".") and p.is_dir()]


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS
