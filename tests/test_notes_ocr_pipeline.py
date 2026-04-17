"""Tests for zoom_assistant.notes_ocr.pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PIL import Image

from zoom_assistant.gemini import GeminiClient
from zoom_assistant.notes_ocr.pipeline import process_folder
from zoom_assistant.notes_ocr.schema import OcrFigure, OcrResponse, OcrSection
from zoom_assistant.notes_ocr.walker import NoteFolder


class _StubClient:
    def __init__(self, response: OcrResponse) -> None:
        self._response = response
        self.polish_calls: list[str] = []

    def generate_structured(self, contents: Any, schema: type[OcrResponse]) -> OcrResponse:
        return self._response

    def polish(self, text: str) -> str:
        self.polish_calls.append(text)
        return text.upper()


def _make_image(path: Path, size: int = 100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (size, size), color=(255, 0, 0)).save(path)
    return path


class TestProcessFolder:
    def test_single_image_no_figures(self, tmp_path: Path) -> None:
        image_path = _make_image(tmp_path / "photo.png")
        response = OcrResponse(
            sections=[OcrSection(heading="Intro", heading_level=2, body="hello world")],
            figures=[],
        )
        stub = _StubClient(response)

        process_folder(
            NoteFolder(path=tmp_path, images=(image_path,)),
            cast(GeminiClient, stub),
        )

        notes_md = (tmp_path / "notes" / "notes.md").read_text()
        assert "# photo.png" in notes_md
        assert "## Intro" in notes_md
        assert "HELLO WORLD" in notes_md
        assert stub.polish_calls == ["hello world"]

    def test_image_with_figure_writes_crop(self, tmp_path: Path) -> None:
        image_path = _make_image(tmp_path / "photo.png", size=200)
        response = OcrResponse(
            sections=[],
            figures=[OcrFigure(x0=0.1, y0=0.1, x1=0.5, y1=0.5, caption="Diagram A")],
        )

        process_folder(
            NoteFolder(path=tmp_path, images=(image_path,)),
            cast(GeminiClient, _StubClient(response)),
        )

        crop_file = tmp_path / "notes" / "assets" / "photo-crop-1.png"
        assert crop_file.exists()
        notes_md = (tmp_path / "notes" / "notes.md").read_text()
        assert "![Diagram A](assets/photo-crop-1.png)" in notes_md

    def test_figure_without_caption_gets_default(self, tmp_path: Path) -> None:
        image_path = _make_image(tmp_path / "photo.png", size=200)
        response = OcrResponse(
            sections=[],
            figures=[OcrFigure(x0=0.0, y0=0.0, x1=1.0, y1=1.0)],
        )

        process_folder(
            NoteFolder(path=tmp_path, images=(image_path,)),
            cast(GeminiClient, _StubClient(response)),
        )

        notes_md = (tmp_path / "notes" / "notes.md").read_text()
        assert "![Figure 1]" in notes_md

    def test_appends_to_existing_notes_md(self, tmp_path: Path) -> None:
        image_path = _make_image(tmp_path / "photo.png")
        response = OcrResponse(sections=[], figures=[])

        notes_md_path = tmp_path / "notes" / "notes.md"
        notes_md_path.parent.mkdir()
        notes_md_path.write_text("EXISTING CONTENT\n")

        process_folder(
            NoteFolder(path=tmp_path, images=(image_path,)),
            cast(GeminiClient, _StubClient(response)),
        )

        contents = notes_md_path.read_text()
        assert contents.startswith("EXISTING CONTENT\n")
        assert "# photo.png" in contents

    def test_stale_crops_cleared_before_new_run(self, tmp_path: Path) -> None:
        image_path = _make_image(tmp_path / "photo.png", size=200)
        assets_dir = tmp_path / "notes" / "assets"
        assets_dir.mkdir(parents=True)
        stale = assets_dir / "photo-crop-3.png"
        stale.write_bytes(b"stale")

        response = OcrResponse(
            sections=[],
            figures=[OcrFigure(x0=0.0, y0=0.0, x1=0.5, y1=0.5)],
        )
        process_folder(
            NoteFolder(path=tmp_path, images=(image_path,)),
            cast(GeminiClient, _StubClient(response)),
        )

        assert not stale.exists()
        assert (assets_dir / "photo-crop-1.png").exists()

    def test_body_only_section_renders_without_heading(self, tmp_path: Path) -> None:
        image_path = _make_image(tmp_path / "photo.png")
        response = OcrResponse(
            sections=[OcrSection(body="plain prose")],
            figures=[],
        )
        stub = _StubClient(response)

        process_folder(
            NoteFolder(path=tmp_path, images=(image_path,)),
            cast(GeminiClient, stub),
        )

        notes_md = (tmp_path / "notes" / "notes.md").read_text()
        assert "PLAIN PROSE" in notes_md
        assert "## " not in notes_md
