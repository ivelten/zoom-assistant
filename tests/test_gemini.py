"""Tests for zoom_assistant.gemini — fallback chain, schema retry, polish guardrail."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import pytest
from google import genai
from pydantic import BaseModel

from zoom_assistant.gemini import (
    GeminiClient,
    GeminiUnavailableError,
    _is_retryable,
    _tokenize_for_guardrail,
    _words_match,
)


class Probe(BaseModel):
    ok: bool


class _StubAPIError(Exception):
    """Exception with a `.code` attribute — mirrors google-genai APIError's duck type."""

    def __init__(self, code: int) -> None:
        super().__init__(f"stub api error {code}")
        self.code = code


class _StubResponse:
    def __init__(self, *, parsed: Any = None, text: str | None = None) -> None:
        self.parsed = parsed
        self.text = text


class _StubModelsAPI:
    def __init__(self, responses: Sequence[object]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate_content(
        self,
        *,
        model: str,
        contents: Sequence[Any],
        config: Any = None,
    ) -> _StubResponse:
        self.calls.append({"model": model, "contents": list(contents), "config": config})
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, _StubResponse)
        return result


class _StubClient:
    def __init__(self, responses: Sequence[object]) -> None:
        self.models = _StubModelsAPI(responses)


_DEFAULT_MODELS: tuple[str, ...] = ("m1", "m2", "m3")


def _make_client(
    responses: Sequence[object], *, models: tuple[str, ...] = _DEFAULT_MODELS
) -> tuple[GeminiClient, _StubClient]:
    stub = _StubClient(responses)
    client = GeminiClient(api_key="test-key", models=models, client=cast(genai.Client, stub))
    return client, stub


class TestIsRetryable:
    @pytest.mark.parametrize("code", [401, 403, 404, 429, 500, 502, 503, 504])
    def test_retryable_status_codes(self, code: int) -> None:
        assert _is_retryable(_StubAPIError(code)) is True

    @pytest.mark.parametrize("code", [400, 410])
    def test_non_retryable_status_codes(self, code: int) -> None:
        assert _is_retryable(_StubAPIError(code)) is False

    def test_generic_exception_not_retryable(self) -> None:
        assert _is_retryable(ValueError("nope")) is False


class TestFallbackChain:
    def test_first_model_succeeds(self) -> None:
        client, stub = _make_client([_StubResponse(parsed=Probe(ok=True))])
        result = client.generate_structured([], Probe)
        assert result == Probe(ok=True)
        assert [c["model"] for c in stub.models.calls] == ["m1"]

    def test_retryable_error_advances_chain(self) -> None:
        client, stub = _make_client([_StubAPIError(429), _StubResponse(parsed=Probe(ok=True))])
        result = client.generate_structured([], Probe)
        assert result == Probe(ok=True)
        assert [c["model"] for c in stub.models.calls] == ["m1", "m2"]

    def test_non_retryable_error_propagates(self) -> None:
        client, _stub = _make_client([_StubAPIError(400)])
        with pytest.raises(_StubAPIError) as exc:
            client.generate_structured([], Probe)
        assert exc.value.code == 400

    def test_all_models_retryable_raises_unavailable(self) -> None:
        client, _stub = _make_client([_StubAPIError(429), _StubAPIError(500), _StubAPIError(503)])
        with pytest.raises(GeminiUnavailableError, match="m1, m2, m3"):
            client.generate_structured([], Probe)


class TestSchemaRetry:
    def test_retry_with_stricter_prompt_then_succeeds(self) -> None:
        client, stub = _make_client(
            [
                _StubResponse(parsed=None, text='{"not_ok": 42}'),
                _StubResponse(parsed=Probe(ok=True)),
            ]
        )
        result = client.generate_structured(["original"], Probe)
        assert result == Probe(ok=True)
        assert len(stub.models.calls) == 2
        assert all(c["model"] == "m1" for c in stub.models.calls)
        second_contents = stub.models.calls[1]["contents"]
        assert any("ONLY valid JSON" in str(c) for c in second_contents)

    def test_schema_failure_twice_falls_through_to_next_model(self) -> None:
        client, stub = _make_client(
            [
                _StubResponse(parsed=None, text='{"not_ok": 42}'),
                _StubResponse(parsed=None, text='{"also_not_ok": true}'),
                _StubResponse(parsed=Probe(ok=True)),
            ]
        )
        result = client.generate_structured([], Probe)
        assert result == Probe(ok=True)
        assert [c["model"] for c in stub.models.calls] == ["m1", "m1", "m2"]


class TestPolishGuardrail:
    def test_polish_empty_short_circuits(self) -> None:
        client, stub = _make_client([])
        assert client.polish("") == ""
        assert client.polish("   ") == "   "
        assert stub.models.calls == []

    def test_polish_passes_guardrail_returns_polished(self) -> None:
        raw = "hello world how are you"
        polished = "Hello, world! How are you?"
        client, _stub = _make_client([_StubResponse(text=polished)])
        assert client.polish(raw) == polished

    def test_polish_fails_guardrail_returns_raw(self) -> None:
        raw = "hello world how are you"
        tampered = "Hello, totally different words entirely."
        client, _stub = _make_client([_StubResponse(text=tampered)])
        assert client.polish(raw) == raw

    def test_polish_all_models_fail_returns_raw(self) -> None:
        raw = "hello world"
        client, _stub = _make_client([_StubAPIError(500), _StubAPIError(500), _StubAPIError(500)])
        assert client.polish(raw) == raw


class TestTokenization:
    def test_strips_punctuation_and_lowercases(self) -> None:
        assert _tokenize_for_guardrail("Hello, World!") == ["hello", "world"]

    def test_multiple_whitespace_collapsed(self) -> None:
        assert _tokenize_for_guardrail("a\n\tb  c") == ["a", "b", "c"]

    def test_empty_input(self) -> None:
        assert _tokenize_for_guardrail("") == []
        assert _tokenize_for_guardrail("   \n ") == []


class TestWordsMatch:
    def test_identical_multiset(self) -> None:
        assert _words_match("hello world", "Hello, world!") is True

    def test_added_word_rejects_on_short_input(self) -> None:
        assert _words_match("hello world foo", "hello world foo bar") is False

    def test_within_tolerance_accepts(self) -> None:
        raw = " ".join(["word"] * 100)
        polished = " ".join(["word"] * 101)
        assert _words_match(raw, polished) is True

    def test_empty_raw_requires_empty_polished(self) -> None:
        assert _words_match("", "") is True
        assert _words_match("", "something") is False
