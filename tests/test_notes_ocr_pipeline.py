"""Tests for zoom_assistant.notes_ocr.pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from PIL import Image

from zoom_assistant.gemini import GeminiClient
from zoom_assistant.notes_ocr.pipeline import list_folder_images, process_folder
from zoom_assistant.notes_ocr.schema import OcrResponse, OcrSection


class _StubClient:
    def __init__(self, responses: list[OcrResponse]) -> None:
        self._responses = list(responses)
        self.ocr_calls: list[list[Any]] = []
        self.polish_calls: list[str] = []

    def generate_structured(self, contents: Any, schema: type[OcrResponse]) -> OcrResponse:
        self.ocr_calls.append(list(contents))
        return self._responses.pop(0)

    def polish(self, text: str) -> str:
        self.polish_calls.append(text)
        return text + "\n<polished>"


def _make_image(
    path: Path, *, size: tuple[int, int] = (40, 40), color: tuple[int, int, int] = (255, 0, 0)
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=color).save(path)
    return path


def _set_ctime(path: Path, epoch: float) -> None:
    os.utime(path, (epoch, epoch))


class TestListFolderImages:
    def test_only_direct_images(self, tmp_path: Path) -> None:
        _make_image(tmp_path / "a.png")
        _make_image(tmp_path / "b.jpg")
        _make_image(tmp_path / "sub" / "ignored.png")
        (tmp_path / "README.txt").write_text("hi")
        images = list_folder_images(tmp_path)
        assert {p.name for p in images} == {"a.png", "b.jpg"}

    def test_dotfiles_ignored(self, tmp_path: Path) -> None:
        _make_image(tmp_path / "a.png")
        _make_image(tmp_path / ".hidden.png")
        images = list_folder_images(tmp_path)
        assert [p.name for p in images] == ["a.png"]

    def test_sorted_oldest_first(self, tmp_path: Path) -> None:
        a = _make_image(tmp_path / "a.png")
        b = _make_image(tmp_path / "b.png")
        c = _make_image(tmp_path / "c.png")
        _set_ctime(b, 1000)
        _set_ctime(a, 2000)
        _set_ctime(c, 3000)
        images = list_folder_images(tmp_path)
        # mtime is the fallback; on macOS birthtime is set at create-time
        # and won't change here, so we read fallback mtime → b<a<c by mtime.
        assert [p.name for p in images] == ["b.png", "a.png", "c.png"]


class TestProcessFolderBatched:
    def test_writes_md_named_after_folder(self, tmp_path: Path) -> None:
        folder = tmp_path / "Aula 04"
        _make_image(folder / "a.png")
        stub = _StubClient([OcrResponse(sections=[OcrSection(body="hello")])])
        out = process_folder(
            folder,
            ocr_client=cast(GeminiClient, stub),
            polish_client=None,
        )
        assert out == folder / "Aula 04.md"
        body = out.read_text()
        assert body.startswith("# Aula 04\n\n")
        assert "hello" in body

    def test_overwrites_existing_md(self, tmp_path: Path) -> None:
        folder = tmp_path / "X"
        _make_image(folder / "a.png")
        existing = folder / "X.md"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("STALE")
        stub = _StubClient([OcrResponse(sections=[OcrSection(body="fresh")])])
        process_folder(folder, ocr_client=cast(GeminiClient, stub), polish_client=None)
        assert "STALE" not in existing.read_text()
        assert "fresh" in existing.read_text()

    def test_no_images_raises(self, tmp_path: Path) -> None:
        folder = tmp_path / "empty"
        folder.mkdir()
        stub = _StubClient([])
        try:
            process_folder(folder, ocr_client=cast(GeminiClient, stub), polish_client=None)
        except ValueError as exc:
            assert "no images" in str(exc).lower()
        else:
            raise AssertionError("expected ValueError")

    def test_sections_aggregated_across_batches(self, tmp_path: Path) -> None:
        folder = tmp_path / "F"
        for i in range(3):
            _make_image(folder / f"img{i}.png", size=(40, 40))
        stub = _StubClient(
            [
                OcrResponse(sections=[OcrSection(body="first")]),
                OcrResponse(sections=[OcrSection(body="second")]),
                OcrResponse(sections=[OcrSection(body="third")]),
            ]
        )
        process_folder(
            folder,
            ocr_client=cast(GeminiClient, stub),
            polish_client=None,
            max_batch_bytes=1,
        )
        body = (folder / "F.md").read_text()
        assert "first" in body
        assert "second" in body
        assert "third" in body
        assert len(stub.ocr_calls) == 3

    def test_polish_called_once_on_full_body(self, tmp_path: Path) -> None:
        folder = tmp_path / "P"
        _make_image(folder / "a.png")
        stub = _StubClient([OcrResponse(sections=[OcrSection(body="raw")])])
        process_folder(
            folder,
            ocr_client=cast(GeminiClient, stub),
            polish_client=cast(GeminiClient, stub),
        )
        assert len(stub.polish_calls) == 1
        assert "# P" in stub.polish_calls[0]
        assert "raw" in stub.polish_calls[0]
        body = (folder / "P.md").read_text()
        assert body.endswith("<polished>")


class TestProcessFolderSingleRequest:
    def test_single_request_makes_one_call_with_one_part(self, tmp_path: Path) -> None:
        folder = tmp_path / "S"
        _make_image(folder / "a.png", size=(30, 40))
        _make_image(folder / "b.png", size=(30, 50))
        _make_image(folder / "c.png", size=(30, 60))
        stub = _StubClient([OcrResponse(sections=[OcrSection(body="all")])])
        process_folder(
            folder,
            ocr_client=cast(GeminiClient, stub),
            polish_client=None,
            single_request=True,
        )
        assert len(stub.ocr_calls) == 1
        # One image part + the prompt string.
        contents = stub.ocr_calls[0]
        assert len(contents) == 2
