"""Pydantic schema for the Gemini OCR response, plus the OCR prompt constant."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

OCR_PROMPT = (
    "You are an OCR system for handwritten or printed notes. Transcribe the "
    "text content in natural reading order, handling multi-column layouts by "
    "reading one column at a time.\n\n"
    "Return JSON matching the response schema:\n"
    "- sections: an ordered list. Each section has an optional heading "
    "(text + level 2 or 3) detected from typographic hierarchy (titles, "
    "card/box labels, bold emphasis), and body prose beneath it. Use level 2 "
    "for the primary title or main section headers; level 3 for subheadings.\n"
    "- figures: bounding boxes in normalized [0, 1] coordinates "
    "(x0, y0, x1, y1) for non-textual regions — photos, diagrams, logos, "
    "hand-drawn sketches. Optional caption describes each figure briefly.\n\n"
    "Rules:\n"
    "- Transcribe ALL readable text, including captions embedded in figures.\n"
    "- Do NOT invent headings — only use what the image visually marks as a "
    "heading.\n"
    "- Preserve numbers, proper nouns, and technical vocabulary exactly.\n"
    "- If the page has no text, return empty sections and one figure covering "
    "the main region.\n"
)


class OcrSection(BaseModel):
    heading: str | None = None
    heading_level: int | None = None
    body: str = ""

    @field_validator("heading_level")
    @classmethod
    def _validate_level(cls, value: int | None) -> int | None:
        if value is not None and not 2 <= value <= 3:
            raise ValueError("heading_level must be 2 or 3")
        return value

    @model_validator(mode="after")
    def _pair_heading_and_level(self) -> OcrSection:
        if (self.heading is None) != (self.heading_level is None):
            raise ValueError("heading and heading_level must be set together")
        return self


class OcrFigure(BaseModel):
    x0: float = Field(ge=0.0, le=1.0)
    y0: float = Field(ge=0.0, le=1.0)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    caption: str | None = None

    @model_validator(mode="after")
    def _validate_box(self) -> OcrFigure:
        if self.x1 <= self.x0:
            raise ValueError("x1 must exceed x0")
        if self.y1 <= self.y0:
            raise ValueError("y1 must exceed y0")
        return self


class OcrResponse(BaseModel):
    sections: list[OcrSection] = Field(default_factory=list)
    figures: list[OcrFigure] = Field(default_factory=list)
