"""Console entry points wired to pyproject.toml's [project.scripts]."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

import click
from rich.logging import RichHandler

from zoom_assistant.config import Config, ConfigError
from zoom_assistant.gemini import GeminiClient
from zoom_assistant.notes_ocr.pipeline import process_folder
from zoom_assistant.notes_ocr.walker import walk_note_folders

logger = logging.getLogger(__name__)


@click.command(name="notes-ocr")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "-j",
    "--jobs",
    type=click.IntRange(min=1),
    default=None,
    help="Images to OCR in parallel per folder. Defaults to min(8, cpu count).",
)
@click.option(
    "--no-polish",
    is_flag=True,
    help="Skip the polish pass for this run; overrides GEMINI_POLISH.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Walk PATH and log what would happen without calling Gemini or writing files.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable DEBUG-level logging.",
)
def notes_ocr_main(
    path: Path,
    jobs: int | None,
    no_polish: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Walk PATH for image folders and emit per-folder Markdown notes."""
    _configure_logging(verbose=verbose)
    if dry_run:
        _run_dry(path)
        return

    resolved_jobs = jobs if jobs is not None else _default_jobs()
    config = _load_config(no_polish=no_polish)
    ocr_client = GeminiClient(api_key=config.primary_api_key, models=config.primary_models)
    polish_client = _build_polish_client(config)

    folders = list(walk_note_folders(path))
    if not folders:
        logger.warning("no note folders found under %s", path)
        return
    for folder in folders:
        logger.info(
            "processing %s (%d images, jobs=%d)",
            folder.path,
            len(folder.images),
            resolved_jobs,
        )
        process_folder(
            folder,
            ocr_client=ocr_client,
            polish_client=polish_client,
            jobs=resolved_jobs,
        )


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


def _configure_logging(*, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
        force=True,
    )


def _default_jobs() -> int:
    return min(8, os.cpu_count() or 1)


def _load_config(*, no_polish: bool) -> Config:
    env: Mapping[str, str] = {**os.environ, "GEMINI_POLISH": "0"} if no_polish else os.environ
    try:
        return Config.for_notes_ocr(env)
    except ConfigError as exc:
        logger.error("configuration error: %s", exc)
        raise click.Abort from exc


def _build_polish_client(config: Config) -> GeminiClient | None:
    if config.polish_api_key is None or config.polish_models is None:
        return None
    return GeminiClient(api_key=config.polish_api_key, models=config.polish_models)


def _run_dry(path: Path) -> None:
    folders = list(walk_note_folders(path))
    if not folders:
        logger.info("no note folders found under %s", path)
        return
    for folder in folders:
        logger.info("would process %s (%d images):", folder.path, len(folder.images))
        for image in folder.images:
            logger.info("  - %s", image.name)
