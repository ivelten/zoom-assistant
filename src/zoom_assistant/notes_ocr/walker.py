"""Recursive walker that yields note folders with their image lists.

Per CLAUDE.md:
- A directory is a note folder iff it contains images directly, OR it has at
  least one direct child that is an "image-leaf" (images + no subdirs).
- A promoted note folder owns its own images plus all images from every
  direct image-leaf child; those leaves don't get their own notes/ output.
- Children with deeper structure recurse independently.
- Merge order within notes.md: by parent-folder name, then by filename.
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
    own_images = _list_images(path)
    leaf_children, recursive_children = _classify_subdirs(path)
    merged = _merge_and_sort(own_images, leaf_children)
    if merged:
        yield NoteFolder(path=path, images=tuple(merged))
    for child in recursive_children:
        yield from _walk(child)


def _classify_subdirs(path: Path) -> tuple[list[Path], list[Path]]:
    leaves: list[Path] = []
    recursive: list[Path] = []
    for subdir in _list_subdirs(path):
        if _is_image_leaf(subdir):
            leaves.append(subdir)
        else:
            recursive.append(subdir)
    return leaves, recursive


def _is_image_leaf(path: Path) -> bool:
    has_image = False
    for entry in path.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            return False
        if _is_image(entry):
            has_image = True
    return has_image


def _list_images(path: Path) -> list[Path]:
    return [p for p in path.iterdir() if not p.name.startswith(".") and _is_image(p)]


def _list_subdirs(path: Path) -> list[Path]:
    return [p for p in path.iterdir() if not p.name.startswith(".") and p.is_dir()]


def _merge_and_sort(own: list[Path], leaves: list[Path]) -> list[Path]:
    all_images: list[Path] = list(own)
    for leaf in leaves:
        all_images.extend(_list_images(leaf))
    return sorted(all_images, key=lambda p: (p.parent.name, p.name))


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS
