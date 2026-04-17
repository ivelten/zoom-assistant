"""Tests for zoom_assistant.config."""

from __future__ import annotations

import pytest

from zoom_assistant.config import Config, ConfigError


def _ocr_env(**overrides: str) -> dict[str, str]:
    base = {
        "NOTES_OCR_GEMINI_API_KEY": "ocr-key",
        "POLISH_GEMINI_API_KEY": "polish-key",
    }
    base.update(overrides)
    return base


def _zoom_env(**overrides: str) -> dict[str, str]:
    base = {
        "ZOOM_NOTES_GEMINI_API_KEY": "zoom-key",
        "POLISH_GEMINI_API_KEY": "polish-key",
    }
    base.update(overrides)
    return base


class TestPerToolFactories:
    def test_notes_ocr_reads_its_own_key(self) -> None:
        config = Config.for_notes_ocr(_ocr_env())
        assert config.primary_api_key == "ocr-key"

    def test_zoom_notes_reads_its_own_key(self) -> None:
        config = Config.for_zoom_notes(_zoom_env())
        assert config.primary_api_key == "zoom-key"

    def test_notes_ocr_does_not_require_zoom_key(self) -> None:
        Config.for_notes_ocr(_ocr_env())  # no ZOOM_NOTES_GEMINI_API_KEY set

    def test_zoom_notes_does_not_require_ocr_key(self) -> None:
        Config.for_zoom_notes(_zoom_env())  # no NOTES_OCR_GEMINI_API_KEY set

    def test_notes_ocr_missing_primary_key_raises(self) -> None:
        with pytest.raises(ConfigError, match="NOTES_OCR_GEMINI_API_KEY"):
            Config.for_notes_ocr({"POLISH_GEMINI_API_KEY": "polish-key"})

    def test_zoom_notes_missing_primary_key_raises(self) -> None:
        with pytest.raises(ConfigError, match="ZOOM_NOTES_GEMINI_API_KEY"):
            Config.for_zoom_notes({"POLISH_GEMINI_API_KEY": "polish-key"})

    def test_blank_primary_key_raises(self) -> None:
        with pytest.raises(ConfigError, match="NOTES_OCR_GEMINI_API_KEY"):
            Config.for_notes_ocr({"NOTES_OCR_GEMINI_API_KEY": "   ", "POLISH_GEMINI_API_KEY": "p"})


class TestPolishKey:
    def test_polish_key_required_when_polish_on(self) -> None:
        with pytest.raises(ConfigError, match="POLISH_GEMINI_API_KEY"):
            Config.for_notes_ocr({"NOTES_OCR_GEMINI_API_KEY": "ocr-key"})

    def test_polish_key_set_when_polish_on(self) -> None:
        config = Config.for_notes_ocr(_ocr_env())
        assert config.polish_api_key == "polish-key"
        assert config.gemini_polish is True

    def test_polish_key_optional_when_polish_off(self) -> None:
        env = {"NOTES_OCR_GEMINI_API_KEY": "ocr-key", "GEMINI_POLISH": "0"}
        config = Config.for_notes_ocr(env)
        assert config.polish_api_key is None
        assert config.gemini_polish is False

    def test_polish_key_also_read_for_zoom_notes(self) -> None:
        config = Config.for_zoom_notes(_zoom_env())
        assert config.polish_api_key == "polish-key"


class TestSharedDefaults:
    def test_defaults_applied(self) -> None:
        config = Config.for_notes_ocr(_ocr_env())
        assert config.gemini_polish is True
        assert config.zoom_notes_mic_device is None
        assert config.zoom_notes_loopback_device is None


class TestPrimaryModels:
    def test_notes_ocr_quality_first_default(self) -> None:
        config = Config.for_notes_ocr(_ocr_env())
        assert config.primary_models[0] == "gemini-2.5-flash"
        assert len(config.primary_models) == 3

    def test_zoom_notes_quality_first_default(self) -> None:
        config = Config.for_zoom_notes(_zoom_env())
        assert config.primary_models[0] == "gemini-2.5-flash"

    def test_notes_ocr_override_respected(self) -> None:
        config = Config.for_notes_ocr(_ocr_env(NOTES_OCR_GEMINI_MODELS=" a , b , c "))
        assert config.primary_models == ("a", "b", "c")

    def test_zoom_notes_override_respected(self) -> None:
        config = Config.for_zoom_notes(_zoom_env(ZOOM_NOTES_GEMINI_MODELS="x,y"))
        assert config.primary_models == ("x", "y")

    def test_notes_ocr_ignores_zoom_models_var(self) -> None:
        config = Config.for_notes_ocr(_ocr_env(ZOOM_NOTES_GEMINI_MODELS="zoom-only"))
        assert "zoom-only" not in config.primary_models

    def test_empty_override_rejected(self) -> None:
        with pytest.raises(ConfigError, match="NOTES_OCR_GEMINI_MODELS"):
            Config.for_notes_ocr(_ocr_env(NOTES_OCR_GEMINI_MODELS=" , , "))


class TestPolishModels:
    def test_cost_first_default(self) -> None:
        config = Config.for_notes_ocr(_ocr_env())
        assert config.polish_models is not None
        assert config.polish_models[0] == "gemini-2.5-flash-lite"
        assert len(config.polish_models) == 3

    def test_override_respected(self) -> None:
        config = Config.for_notes_ocr(_ocr_env(POLISH_GEMINI_MODELS="lite-x,lite-y"))
        assert config.polish_models == ("lite-x", "lite-y")

    def test_polish_models_shared_across_tools(self) -> None:
        notes_ocr = Config.for_notes_ocr(_ocr_env(POLISH_GEMINI_MODELS="shared"))
        zoom_notes = Config.for_zoom_notes(_zoom_env(POLISH_GEMINI_MODELS="shared"))
        assert notes_ocr.polish_models == ("shared",)
        assert zoom_notes.polish_models == ("shared",)

    def test_none_when_polish_disabled(self) -> None:
        env = {"NOTES_OCR_GEMINI_API_KEY": "ocr-key", "GEMINI_POLISH": "0"}
        config = Config.for_notes_ocr(env)
        assert config.polish_models is None

    def test_empty_override_rejected(self) -> None:
        with pytest.raises(ConfigError, match="POLISH_GEMINI_MODELS"):
            Config.for_notes_ocr(_ocr_env(POLISH_GEMINI_MODELS=" , , "))


class TestPolishBoolParsing:
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
    def test_valid_values(self, raw: str, expected: bool) -> None:
        env: dict[str, str] = {
            "NOTES_OCR_GEMINI_API_KEY": "ocr-key",
            "GEMINI_POLISH": raw,
        }
        if expected:
            env["POLISH_GEMINI_API_KEY"] = "polish-key"
        config = Config.for_notes_ocr(env)
        assert config.gemini_polish is expected

    def test_blank_uses_default(self) -> None:
        config = Config.for_notes_ocr(_ocr_env(GEMINI_POLISH="  "))
        assert config.gemini_polish is True

    def test_bad_value_rejected(self) -> None:
        with pytest.raises(ConfigError, match="GEMINI_POLISH"):
            Config.for_notes_ocr(_ocr_env(GEMINI_POLISH="maybe"))


class TestZoomDeviceParsing:
    def test_optional_int_parsed(self) -> None:
        config = Config.for_zoom_notes(
            _zoom_env(ZOOM_NOTES_MIC_DEVICE="3", ZOOM_NOTES_LOOPBACK_DEVICE="7")
        )
        assert config.zoom_notes_mic_device == 3
        assert config.zoom_notes_loopback_device == 7

    def test_optional_int_rejects_non_integer(self) -> None:
        with pytest.raises(ConfigError, match="ZOOM_NOTES_MIC_DEVICE"):
            Config.for_zoom_notes(_zoom_env(ZOOM_NOTES_MIC_DEVICE="abc"))
