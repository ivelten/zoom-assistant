"""Environment-variable loading and validation for zoom-assistant.

`Config.from_env()` is called once at process start. It fails fast with a
`ConfigError` if `GEMINI_API_KEY` is missing or if any optional variable is
malformed.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Raised when required environment variables are missing or malformed."""


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

_DEFAULT_MODELS = "gemini-2.5-flash,gemini-2.0-flash"


@dataclass(frozen=True, slots=True)
class Config:
    gemini_api_key: str
    gemini_models: tuple[str, ...]
    gemini_polish: bool
    zoom_notes_mic_device: int | None
    zoom_notes_loopback_device: int | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        source: Mapping[str, str] = os.environ if env is None else env
        return cls(
            gemini_api_key=_require(source, "GEMINI_API_KEY"),
            gemini_models=_parse_models(source.get("GEMINI_MODELS") or _DEFAULT_MODELS),
            gemini_polish=_parse_bool(
                source.get("GEMINI_POLISH"), default=True, name="GEMINI_POLISH"
            ),
            zoom_notes_mic_device=_parse_optional_int(
                source.get("ZOOM_NOTES_MIC_DEVICE"), name="ZOOM_NOTES_MIC_DEVICE"
            ),
            zoom_notes_loopback_device=_parse_optional_int(
                source.get("ZOOM_NOTES_LOOPBACK_DEVICE"), name="ZOOM_NOTES_LOOPBACK_DEVICE"
            ),
        )


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required but not set")
    return value


def _parse_models(raw: str) -> tuple[str, ...]:
    models = tuple(m.strip() for m in raw.split(",") if m.strip())
    if not models:
        raise ConfigError("GEMINI_MODELS must list at least one model id")
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
