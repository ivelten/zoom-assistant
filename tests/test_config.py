"""Tests for zoom_assistant.config."""

from __future__ import annotations

import pytest

from zoom_assistant.config import Config, ConfigError


def _base_env(**overrides: str) -> dict[str, str]:
    base = {"GEMINI_API_KEY": "test-key"}
    base.update(overrides)
    return base


def test_missing_api_key_raises() -> None:
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        Config.from_env({})


def test_blank_api_key_raises() -> None:
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        Config.from_env({"GEMINI_API_KEY": "   "})


def test_defaults_applied() -> None:
    config = Config.from_env(_base_env())
    assert config.gemini_api_key == "test-key"
    assert config.gemini_models == ("gemini-2.5-flash", "gemini-2.0-flash")
    assert config.gemini_polish is True
    assert config.zoom_notes_mic_device is None
    assert config.zoom_notes_loopback_device is None


def test_models_parsed_and_trimmed() -> None:
    config = Config.from_env(_base_env(GEMINI_MODELS=" a , b , c "))
    assert config.gemini_models == ("a", "b", "c")


def test_empty_models_list_rejected() -> None:
    with pytest.raises(ConfigError, match="GEMINI_MODELS"):
        Config.from_env(_base_env(GEMINI_MODELS=" , , "))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("0", False),
        ("true", True),
        ("FALSE", False),
        ("yes", True),
        ("no", False),
        ("ON", True),
        ("off", False),
    ],
)
def test_polish_bool_parsed(raw: str, expected: bool) -> None:
    config = Config.from_env(_base_env(GEMINI_POLISH=raw))
    assert config.gemini_polish is expected


def test_polish_blank_uses_default() -> None:
    config = Config.from_env(_base_env(GEMINI_POLISH="  "))
    assert config.gemini_polish is True


def test_polish_bad_value_rejected() -> None:
    with pytest.raises(ConfigError, match="GEMINI_POLISH"):
        Config.from_env(_base_env(GEMINI_POLISH="maybe"))


def test_optional_int_parsed() -> None:
    config = Config.from_env(_base_env(ZOOM_NOTES_MIC_DEVICE="3", ZOOM_NOTES_LOOPBACK_DEVICE="7"))
    assert config.zoom_notes_mic_device == 3
    assert config.zoom_notes_loopback_device == 7


def test_optional_int_rejects_non_integer() -> None:
    with pytest.raises(ConfigError, match="ZOOM_NOTES_MIC_DEVICE"):
        Config.from_env(_base_env(ZOOM_NOTES_MIC_DEVICE="abc"))
