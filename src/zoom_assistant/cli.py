"""Console entry points wired to pyproject.toml's [project.scripts]."""

from __future__ import annotations

from pathlib import Path

import click


@click.command(name="notes-ocr")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
def notes_ocr_main(path: Path) -> None:
    """Walk PATH for image folders and emit per-folder Markdown notes."""
    raise NotImplementedError("notes-ocr pipeline lands in a later phase")


@click.command(name="zoom-notes")
@click.argument(
    "output_path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path(),
    required=False,
)
def zoom_notes_main(output_path: Path) -> None:
    """Capture a live Zoom meeting and write a Markdown transcript to OUTPUT_PATH."""
    raise NotImplementedError("zoom-notes pipeline lands in a later phase")
