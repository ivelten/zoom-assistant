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

logger = logging.getLogger(__name__)


@click.command(name="notes-ocr")
@click.argument(
    "folder",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "-s",
    "--single-request",
    is_flag=True,
    help="Stitch all images into one tall PNG and send a single OCR request.",
)
@click.option(
    "--no-polish",
    is_flag=True,
    help="Skip the polish pass for this run; overrides GEMINI_POLISH.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="List the images that would be OCR'd without calling Gemini or writing files.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable DEBUG-level logging.",
)
def notes_ocr_main(
    folder: Path,
    single_request: bool,
    no_polish: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    """OCR every image in FOLDER and write FOLDER/<folder-name>.md.

    Images directly inside FOLDER (not subfolders) are processed in
    creation-time order. By default, images are sent to Gemini in
    multi-image batches up to ~15 MB per request; --single-request
    stitches them all into one tall PNG and sends a single request.
    """
    _configure_logging(verbose=verbose)
    if dry_run:
        _run_dry(folder)
        return

    config = _load_config(no_polish=no_polish)
    ocr_client = GeminiClient(api_key=config.primary_api_key, models=config.primary_models)
    polish_client = _build_polish_client(config)

    output_path = process_folder(
        folder,
        ocr_client=ocr_client,
        polish_client=polish_client,
        single_request=single_request,
    )
    logger.info("wrote %s", output_path)


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


def _run_dry(folder: Path) -> None:
    from zoom_assistant.notes_ocr.pipeline import list_folder_images

    images = list_folder_images(folder)
    if not images:
        logger.warning("no images found in %s", folder)
        return
    logger.info(
        "would OCR %d images from %s and write %s",
        len(images),
        folder,
        folder / f"{folder.name}.md",
    )
    for image in images:
        logger.info("  - %s", image.name)
