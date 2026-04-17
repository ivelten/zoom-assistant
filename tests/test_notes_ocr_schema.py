"""Tests for zoom_assistant.notes_ocr.schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from zoom_assistant.notes_ocr.schema import OCR_PROMPT, OcrResponse, OcrSection


class TestOcrSection:
    def test_heading_with_level(self) -> None:
        section = OcrSection(heading="Intro", heading_level=2, body="hi")
        assert section.heading == "Intro"
        assert section.heading_level == 2

    def test_body_only(self) -> None:
        section = OcrSection(body="just text")
        assert section.heading is None
        assert section.heading_level is None

    def test_heading_without_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OcrSection(heading="Intro", body="hi")

    def test_level_without_heading_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OcrSection(heading_level=2, body="hi")

    @pytest.mark.parametrize("level", [1, 4, 5, 6])
    def test_invalid_level_rejected(self, level: int) -> None:
        with pytest.raises(ValidationError):
            OcrSection(heading="x", heading_level=level, body="")


class TestOcrResponse:
    def test_parses_from_json(self) -> None:
        json_str = '{"sections": [{"body": "hi"}]}'
        response = OcrResponse.model_validate_json(json_str)
        assert response.sections[0].body == "hi"

    def test_defaults_empty(self) -> None:
        response = OcrResponse()
        assert response.sections == []


def test_ocr_prompt_mentions_schema_fields() -> None:
    assert "sections" in OCR_PROMPT
