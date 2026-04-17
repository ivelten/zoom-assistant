"""Tests for zoom_assistant.notes_ocr.pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PIL import Image

from zoom_assistant.gemini import GeminiClient
from zoom_assistant.notes_ocr.pipeline import process_folder
from zoom_assistant.notes_ocr.schema import OcrResponse, OcrSection
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
    def test_single_image_with_heading_and_body(self, tmp_path: Path) -> None:
        image_path = _make_image(tmp_path / "photo.png")
        response = OcrResponse(
            sections=[OcrSection(heading="Intro", heading_level=2, body="hello world")]
        )
        stub = _StubClient(response)

        process_folder(
            NoteFolder(path=tmp_path, images=(image_path,)),
            ocr_client=cast(GeminiClient, stub),
            polish_client=cast(GeminiClient, stub),
        )

        notes_md = (tmp_path / "notes" / "notes.md").read_text()
        assert "# photo.png" in notes_md
        assert "## Intro" in notes_md
        assert "HELLO WORLD" in notes_md
        assert stub.polish_calls == ["hello world"]

    def test_appends_to_existing_notes_md(self, tmp_path: Path) -> None:
        image_path = _make_image(tmp_path / "photo.png")
        response = OcrResponse(sections=[])

        notes_md_path = tmp_path / "notes" / "notes.md"
        notes_md_path.parent.mkdir()
        notes_md_path.write_text("EXISTING CONTENT\n")

        stub = _StubClient(response)
        process_folder(
            NoteFolder(path=tmp_path, images=(image_path,)),
            ocr_client=cast(GeminiClient, stub),
            polish_client=cast(GeminiClient, stub),
        )

        contents = notes_md_path.read_text()
        assert contents.startswith("EXISTING CONTENT\n")
        assert "# photo.png" in contents

    def test_body_only_section_renders_without_heading(self, tmp_path: Path) -> None:
        image_path = _make_image(tmp_path / "photo.png")
        response = OcrResponse(sections=[OcrSection(body="plain prose")])
        stub = _StubClient(response)

        process_folder(
            NoteFolder(path=tmp_path, images=(image_path,)),
            ocr_client=cast(GeminiClient, stub),
            polish_client=cast(GeminiClient, stub),
        )

        notes_md = (tmp_path / "notes" / "notes.md").read_text()
        assert "PLAIN PROSE" in notes_md
        assert "## " not in notes_md

    def test_polish_client_none_skips_polish(self, tmp_path: Path) -> None:
        image_path = _make_image(tmp_path / "photo.png")
        response = OcrResponse(sections=[OcrSection(body="raw body text")])
        stub = _StubClient(response)

        process_folder(
            NoteFolder(path=tmp_path, images=(image_path,)),
            ocr_client=cast(GeminiClient, stub),
            polish_client=None,
        )

        notes_md = (tmp_path / "notes" / "notes.md").read_text()
        assert "raw body text" in notes_md
        assert "RAW BODY TEXT" not in notes_md
        assert stub.polish_calls == []

    def test_no_assets_directory_created(self, tmp_path: Path) -> None:
        image_path = _make_image(tmp_path / "photo.png")
        response = OcrResponse(sections=[OcrSection(body="hi")])

        process_folder(
            NoteFolder(path=tmp_path, images=(image_path,)),
            ocr_client=cast(GeminiClient, _StubClient(response)),
            polish_client=cast(GeminiClient, _StubClient(response)),
        )

        assert not (tmp_path / "notes" / "assets").exists()
