"""Gemini client wrapper: model-fallback chain, schema-retry, and polish pass.

Every Gemini call in this project goes through `GeminiClient`. One instance
per purpose — OCR, transcription, or polish — each constructed with its own
API key so usage can be monitored per-purpose. It handles:

- Iterating `GEMINI_MODELS` on retryable failures (401/403/429/5xx + transport).
- Retrying a schema-validated call once on the *same* model with a stricter
  prompt before advancing the chain to the next model.
- Polishing raw OCR/transcript text through a strict "punctuation and
  paragraphs only" prompt, with a ≤2% word-count guardrail that falls back
  to the raw text if violated. Whether to polish at all is the caller's
  decision (pass a polish client, or don't); this class always tries.
"""

from __future__ import annotations

import logging
import string
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = frozenset({401, 403, 404, 429, 500, 502, 503, 504})
_POLISH_TOLERANCE = 0.02
_PUNCT_TRANSLATION = str.maketrans("", "", string.punctuation)

_POLISH_INSTRUCTIONS = (
    "You are a text formatter. Your only job is to add "
    "punctuation (periods, commas,\n"
    "question marks, quotation marks), correct capitalization at sentence starts,\n"
    "and split the text into paragraphs at natural boundaries.\n"
    "\n"
    "STRICT RULES:\n"
    "- Do NOT add, remove, replace, or rephrase any word.\n"
    "- Preserve all numbers, proper nouns, technical terms, abbreviations, and\n"
    "  domain-specific vocabulary exactly as given.\n"
    "- Do NOT add headings, commentary, or any content of your own.\n"
    "- Do NOT fix grammar if doing so would change any word.\n"
    "- Output only the reformatted text, nothing else.\n"
    "\n"
    "INPUT:\n"
)

_STRICTER_JSON_HEADER = (
    "Return ONLY valid JSON that exactly matches the provided response schema. "
    "Do not include markdown fences, commentary, or any text outside the JSON object.\n\n"
)


class GeminiUnavailableError(RuntimeError):
    """Raised when every model in `GEMINI_MODELS` failed with retryable errors."""


class _SchemaValidationError(Exception):
    """Gemini response failed pydantic validation on a given model attempt."""


class _SchemaRetryExhaustedError(Exception):
    """Strict retry on the same model also failed validation; advance the chain."""


T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        models: Sequence[str],
        client: genai.Client | None = None,
    ) -> None:
        self._models = tuple(models)
        self._client = client if client is not None else genai.Client(api_key=api_key)

    def generate_structured(
        self,
        contents: Sequence[types.Part | str],
        schema: type[M],
    ) -> M:
        """Run a JSON-schema-validated Gemini call with fallback + strict retry."""

        def attempt(model: str) -> M:
            try:
                return self._structured_call(model, contents, schema, strict=False)
            except _SchemaValidationError:
                logger.warning(
                    "schema validation failed on %s; retrying with stricter prompt", model
                )
            try:
                return self._structured_call(model, contents, schema, strict=True)
            except _SchemaValidationError as exc:
                logger.warning(
                    "schema validation failed on %s after strict retry; advancing chain",
                    model,
                )
                raise _SchemaRetryExhaustedError(str(exc)) from exc

        return self._call_with_fallback(attempt)

    def polish(self, text: str) -> str:
        """Reformat `text` with punctuation and paragraphs; never changes words.

        Returns `text` unchanged if the input is whitespace-only, the output
        fails the ≤2% word-count guardrail, or every model in the chain
        errored. Whether to call this method at all is the caller's decision.
        """
        if not text.strip():
            return text
        try:
            polished = self._call_with_fallback(lambda m: self._polish_call(m, text))
        except GeminiUnavailableError:
            logger.error("polish: every model errored; keeping raw text")
            return text
        if _words_match(text, polished):
            return polished
        logger.warning("polish: word-count guardrail failed; keeping raw text")
        return text

    def _call_with_fallback(self, attempt: Callable[[str], T]) -> T:
        last_exc: BaseException | None = None
        for model in self._models:
            try:
                return attempt(model)
            except Exception as exc:
                if not _is_retryable(exc):
                    raise
                logger.warning("gemini model %s hit retryable error: %s", model, exc)
                last_exc = exc
        raise GeminiUnavailableError(
            f"every model in GEMINI_MODELS failed: {', '.join(self._models)}"
        ) from last_exc

    def _structured_call(
        self,
        model: str,
        contents: Sequence[types.Part | str],
        schema: type[M],
        *,
        strict: bool,
    ) -> M:
        prepared: list[Any] = [_STRICTER_JSON_HEADER, *contents] if strict else list(contents)
        response = self._client.models.generate_content(
            model=model,
            contents=prepared,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        return _parse_structured_response(response, schema)

    def _polish_call(self, model: str, text: str) -> str:
        prepared: list[Any] = [_POLISH_INSTRUCTIONS + text]
        response = self._client.models.generate_content(
            model=model,
            contents=prepared,
        )
        return (response.text or "").strip()


def _parse_structured_response[ModelT: BaseModel](
    response: types.GenerateContentResponse, schema: type[ModelT]
) -> ModelT:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    raw_text = getattr(response, "text", None) or ""
    try:
        return schema.model_validate_json(raw_text)
    except ValidationError as exc:
        raise _SchemaValidationError(str(exc)) from exc


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, _SchemaRetryExhaustedError):
        return True
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code in _RETRYABLE_STATUS_CODES
    return isinstance(exc, httpx.TransportError)


def _tokenize_for_guardrail(text: str) -> list[str]:
    normalized = text.translate(_PUNCT_TRANSLATION).lower()
    return [tok for tok in normalized.split() if tok]


def _words_match(raw: str, polished: str, tolerance: float = _POLISH_TOLERANCE) -> bool:
    raw_tokens = Counter(_tokenize_for_guardrail(raw))
    polished_tokens = Counter(_tokenize_for_guardrail(polished))
    total_raw = sum(raw_tokens.values())
    if total_raw == 0:
        return sum(polished_tokens.values()) == 0
    diff = (raw_tokens - polished_tokens) + (polished_tokens - raw_tokens)
    return sum(diff.values()) / total_raw <= tolerance
