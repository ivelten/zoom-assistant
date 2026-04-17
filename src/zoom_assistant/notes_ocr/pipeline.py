"""notes-ocr pipeline: per-folder OCR, figure crops, polished markdown sections."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from google.genai import types
from PIL import Image

from zoom_assistant.gemini import GeminiClient
from zoom_assistant.image import (
    NormalizedBox,
    crop_normalized,
    guess_mime_type,
    load_image,
    read_bytes,
    write_png,
)
from zoom_assistant.markdown import (
    FigureLink,
    Heading,
    ImageNote,
    Section,
    render_image_note,
)
from zoom_assistant.notes_ocr.schema import (
    OCR_PROMPT,
    OcrFigure,
    OcrResponse,
    OcrSection,
)
from zoom_assistant.notes_ocr.walker import NoteFolder

logger = logging.getLogger(__name__)

_NOTES_DIRNAME = "notes"
_ASSETS_DIRNAME = "assets"
_NOTES_FILENAME = "notes.md"


def process_folder(folder: NoteFolder, client: GeminiClient) -> None:
    """OCR every image in `folder` and append sections to its notes.md.

    Creates `notes/` and `notes/assets/` under the folder as needed. notes.md
    is opened in append mode so repeated runs accumulate sections.
    """
    notes_dir = folder.path / _NOTES_DIRNAME
    assets_dir = notes_dir / _ASSETS_DIRNAME
    notes_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    with (notes_dir / _NOTES_FILENAME).open("a", encoding="utf-8") as fp:
        for image_path in folder.images:
            note = _ocr_single_image(image_path, assets_dir, client)
            fp.write(render_image_note(note))


def _ocr_single_image(image_path: Path, assets_dir: Path, client: GeminiClient) -> ImageNote:
    logger.info("ocr: %s", image_path)
    image = load_image(image_path)
    part = types.Part.from_bytes(data=read_bytes(image_path), mime_type=guess_mime_type(image_path))
    response = client.generate_structured([part, OCR_PROMPT], OcrResponse)
    _clear_stale_crops(assets_dir, image_path.stem)
    figure_links = _write_figure_crops(image, image_path, assets_dir, response.figures)
    sections = tuple(_polish_section(s, client) for s in response.sections)
    return ImageNote(
        filename=image_path.name,
        taken_at=_image_mtime(image_path),
        sections=sections,
        figures=figure_links,
    )


def _polish_section(section: OcrSection, client: GeminiClient) -> Section:
    return Section(heading=_to_heading(section), body=client.polish(section.body))


def _to_heading(section: OcrSection) -> Heading | None:
    if section.heading is None or section.heading_level is None:
        return None
    return Heading(level=section.heading_level, text=section.heading)


def _write_figure_crops(
    image: Image.Image,
    source: Path,
    assets_dir: Path,
    figures: list[OcrFigure],
) -> tuple[FigureLink, ...]:
    links: list[FigureLink] = []
    for index, figure in enumerate(figures, start=1):
        box = NormalizedBox(figure.x0, figure.y0, figure.x1, figure.y1)
        crop = crop_normalized(image, box)
        crop_path = assets_dir / f"{source.stem}-crop-{index}.png"
        write_png(crop, crop_path)
        caption = figure.caption or f"Figure {index}"
        links.append(
            FigureLink(caption=caption, relative_path=f"{_ASSETS_DIRNAME}/{crop_path.name}")
        )
    return tuple(links)


def _clear_stale_crops(assets_dir: Path, image_stem: str) -> None:
    for stale in assets_dir.glob(f"{image_stem}-crop-*.png"):
        stale.unlink()


def _image_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone()
