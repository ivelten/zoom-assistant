"""notes-ocr pipeline: per-folder OCR via batched or stitched Gemini requests."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from pathlib import Path

from google.genai import types

from zoom_assistant.gemini import GeminiClient
from zoom_assistant.image import guess_mime_type, stitch_vertical
from zoom_assistant.markdown import (
    FolderNote,
    Heading,
    Section,
    render_folder_note,
)
from zoom_assistant.notes_ocr.schema import OCR_PROMPT, OcrResponse, OcrSection

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg"})
_DEFAULT_BATCH_BYTES = 15_000_000


def list_folder_images(folder: Path) -> list[Path]:
    """Return image files directly inside `folder`, oldest first by birthtime.

    Subfolders, hidden entries, and non-image files are ignored. Falls back
    to mtime when the OS doesn't expose a creation timestamp.
    """
    images = [
        entry
        for entry in folder.iterdir()
        if entry.is_file()
        and not entry.name.startswith(".")
        and entry.suffix.lower() in _IMAGE_EXTENSIONS
    ]
    return sorted(images, key=_creation_time)


def process_folder(
    folder: Path,
    *,
    ocr_client: GeminiClient,
    polish_client: GeminiClient | None,
    single_request: bool = False,
    max_batch_bytes: int = _DEFAULT_BATCH_BYTES,
) -> Path:
    """OCR every image in `folder` and write `<folder>/<folder-name>.md`.

    `ocr_client` runs the OCR call(s); `polish_client` runs one polish pass
    over the rendered markdown body (skipped when `polish_client=None`).
    `single_request=True` stitches all images into one tall PNG and sends a
    single OCR request; otherwise images are batched up to
    `max_batch_bytes` per request. Returns the path to the written .md.
    """
    images = list_folder_images(folder)
    if not images:
        raise ValueError(f"no images found in {folder}")
    sections = _ocr_images(images, ocr_client, single_request, max_batch_bytes)
    note = FolderNote(title=folder.name, sections=tuple(sections))
    body = render_folder_note(note)
    if polish_client is not None:
        body = polish_client.polish(body)
    output_path = folder / f"{folder.name}.md"
    output_path.write_text(body, encoding="utf-8")
    return output_path


def _ocr_images(
    images: Sequence[Path],
    ocr_client: GeminiClient,
    single_request: bool,
    max_batch_bytes: int,
) -> list[Section]:
    if single_request:
        logger.info("ocr (stitched): %d images", len(images))
        return _ocr_call(_stitched_parts(images), ocr_client)
    sections: list[Section] = []
    for batch in _batches(images, max_batch_bytes):
        logger.info("ocr (batch): %d images", len(batch))
        sections.extend(_ocr_call(_image_parts(batch), ocr_client))
    return sections


def _ocr_call(parts: list[types.Part], ocr_client: GeminiClient) -> list[Section]:
    contents: list[types.Part | str] = [*parts, OCR_PROMPT]
    response = ocr_client.generate_structured(contents, OcrResponse)
    return [_to_section(s) for s in response.sections]


def _stitched_parts(images: Sequence[Path]) -> list[types.Part]:
    stitched_bytes = stitch_vertical(images)
    return [types.Part.from_bytes(data=stitched_bytes, mime_type="image/png")]


def _image_parts(images: Sequence[Path]) -> list[types.Part]:
    return [
        types.Part.from_bytes(data=image.read_bytes(), mime_type=guess_mime_type(image))
        for image in images
    ]


def _batches(images: Sequence[Path], max_bytes: int) -> Iterator[list[Path]]:
    batch: list[Path] = []
    batch_bytes = 0
    for image in images:
        size = image.stat().st_size
        if batch and batch_bytes + size > max_bytes:
            yield batch
            batch = []
            batch_bytes = 0
        batch.append(image)
        batch_bytes += size
    if batch:
        yield batch


def _to_section(section: OcrSection) -> Section:
    return Section(heading=_to_heading(section), body=section.body)


def _to_heading(section: OcrSection) -> Heading | None:
    if section.heading is None or section.heading_level is None:
        return None
    return Heading(level=section.heading_level, text=section.heading)


def _creation_time(path: Path) -> float:
    stat = path.stat()
    return getattr(stat, "st_birthtime", stat.st_mtime)
