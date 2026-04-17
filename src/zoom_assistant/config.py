"""Environment-variable loading and validation for zoom-assistant.

Each Gemini usage pattern (OCR, transcription, polish) gets its own API
key AND its own model-fallback chain so usage can be monitored *and* tuned
per-purpose:

- `NOTES_OCR_GEMINI_API_KEY` + `NOTES_OCR_GEMINI_MODELS` — image OCR in
  `notes-ocr`.
- `ZOOM_NOTES_GEMINI_API_KEY` + `ZOOM_NOTES_GEMINI_MODELS` — audio
  transcription in `zoom-notes`.
- `POLISH_GEMINI_API_KEY` + `POLISH_GEMINI_MODELS` — shared polish pass,
  used by both tools when `GEMINI_POLISH=1` (the default).

Defaults keep OCR/transcription on quality-first chains and polish on a
cost-first chain; override any of them via the matching env var.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Raised when required environment variables are missing or malformed."""


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

_DEFAULT_PRIMARY_MODELS = "gemini-2.5-flash,gemini-2.0-flash,gemini-2.5-flash-lite"
_DEFAULT_POLISH_MODELS = "gemini-2.5-flash-lite,gemini-2.0-flash,gemini-2.5-flash"

_NOTES_OCR_KEY_VAR = "NOTES_OCR_GEMINI_API_KEY"
_ZOOM_NOTES_KEY_VAR = "ZOOM_NOTES_GEMINI_API_KEY"
_POLISH_KEY_VAR = "POLISH_GEMINI_API_KEY"

_NOTES_OCR_MODELS_VAR = "NOTES_OCR_GEMINI_MODELS"
_ZOOM_NOTES_MODELS_VAR = "ZOOM_NOTES_GEMINI_MODELS"
_POLISH_MODELS_VAR = "POLISH_GEMINI_MODELS"


@dataclass(frozen=True, slots=True)
class Config:
    primary_api_key: str
    primary_models: tuple[str, ...]
    polish_api_key: str | None
    polish_models: tuple[str, ...] | None
    gemini_polish: bool
    zoom_notes_mic_device: int | None
    zoom_notes_loopback_device: int | None

    @classmethod
    def for_notes_ocr(cls, env: Mapping[str, str] | None = None) -> Config:
        return cls._from_env(
            env,
            primary_key_var=_NOTES_OCR_KEY_VAR,
            primary_models_var=_NOTES_OCR_MODELS_VAR,
        )

    @classmethod
    def for_zoom_notes(cls, env: Mapping[str, str] | None = None) -> Config:
        return cls._from_env(
            env,
            primary_key_var=_ZOOM_NOTES_KEY_VAR,
            primary_models_var=_ZOOM_NOTES_MODELS_VAR,
        )

    @classmethod
    def _from_env(
        cls,
        env: Mapping[str, str] | None,
        *,
        primary_key_var: str,
        primary_models_var: str,
    ) -> Config:
        source: Mapping[str, str] = os.environ if env is None else env
        polish = _parse_bool(source.get("GEMINI_POLISH"), default=True, name="GEMINI_POLISH")
        return cls(
            primary_api_key=_require(source, primary_key_var),
            primary_models=_parse_models(
                source.get(primary_models_var) or _DEFAULT_PRIMARY_MODELS,
                name=primary_models_var,
            ),
            polish_api_key=_require(source, _POLISH_KEY_VAR) if polish else None,
            polish_models=(
                _parse_models(
                    source.get(_POLISH_MODELS_VAR) or _DEFAULT_POLISH_MODELS,
                    name=_POLISH_MODELS_VAR,
                )
                if polish
                else None
            ),
            gemini_polish=polish,
            zoom_notes_mic_device=_parse_optional_int(
                source.get("ZOOM_NOTES_MIC_DEVICE"), name="ZOOM_NOTES_MIC_DEVICE"
            ),
            zoom_notes_loopback_device=_parse_optional_int(
                source.get("ZOOM_NOTES_LOOPBACK_DEVICE"),
                name="ZOOM_NOTES_LOOPBACK_DEVICE",
            ),
        )


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required but not set")
    return value


def _parse_models(raw: str, *, name: str) -> tuple[str, ...]:
    models = tuple(m.strip() for m in raw.split(",") if m.strip())
    if not models:
        raise ConfigError(f"{name} must list at least one model id")
    return models


def _parse_bool(raw: str | None, *, default: bool, name: str) -> bool:
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ConfigError(f"{name} must be one of 1/0/true/false/yes/no/on/off, got {raw!r}")


def _parse_optional_int(raw: str | None, *, name: str) -> int | None:
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer or unset, got {raw!r}") from exc
