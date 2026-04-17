"""Tests for zoom_assistant.cli — notes-ocr CLI wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from zoom_assistant import cli
from zoom_assistant.cli import notes_ocr_main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def note_folder(tmp_path: Path) -> Path:
    (tmp_path / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return tmp_path


@pytest.fixture
def mocks(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Swap GeminiClient and process_folder for trivial mocks."""
    gc_mock = MagicMock(name="GeminiClient")
    pf_calls: list[dict[str, Any]] = []

    def record_call(*args: Any, **kwargs: Any) -> None:
        pf_calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(cli, "GeminiClient", gc_mock)
    monkeypatch.setattr(cli, "process_folder", record_call)
    return {"GeminiClient": gc_mock, "process_folder_calls": pf_calls}


def _set_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTES_OCR_GEMINI_API_KEY", "ocr-key")
    monkeypatch.setenv("POLISH_GEMINI_API_KEY", "polish-key")


class TestPathValidation:
    def test_missing_path_exits_non_zero(self, runner: CliRunner) -> None:
        result = runner.invoke(notes_ocr_main, ["/does/not/exist"])
        assert result.exit_code != 0

    def test_file_instead_of_directory_rejected(self, runner: CliRunner, tmp_path: Path) -> None:
        file = tmp_path / "a.txt"
        file.write_text("hi")
        result = runner.invoke(notes_ocr_main, [str(file)])
        assert result.exit_code != 0


class TestDryRun:
    def test_does_not_construct_clients_or_process(
        self,
        runner: CliRunner,
        note_folder: Path,
        mocks: dict[str, Any],
    ) -> None:
        result = runner.invoke(notes_ocr_main, [str(note_folder), "--dry-run"])
        assert result.exit_code == 0
        assert mocks["GeminiClient"].call_count == 0
        assert mocks["process_folder_calls"] == []

    def test_dry_run_does_not_require_env_vars(
        self,
        runner: CliRunner,
        note_folder: Path,
        mocks: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("NOTES_OCR_GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("POLISH_GEMINI_API_KEY", raising=False)
        result = runner.invoke(notes_ocr_main, [str(note_folder), "--dry-run"])
        assert result.exit_code == 0


class TestConfigErrors:
    def test_missing_api_key_exits_with_error(
        self,
        runner: CliRunner,
        note_folder: Path,
        mocks: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("NOTES_OCR_GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("POLISH_GEMINI_API_KEY", raising=False)
        result = runner.invoke(notes_ocr_main, [str(note_folder)])
        assert result.exit_code != 0
        assert mocks["process_folder_calls"] == []


class TestHappyPath:
    def test_calls_process_folder_once_per_note_folder(
        self,
        runner: CliRunner,
        note_folder: Path,
        mocks: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_keys(monkeypatch)
        result = runner.invoke(notes_ocr_main, [str(note_folder)])
        assert result.exit_code == 0
        assert len(mocks["process_folder_calls"]) == 1
        kwargs = mocks["process_folder_calls"][0]["kwargs"]
        assert kwargs["polish_client"] is not None
        assert "ocr_client" in kwargs

    def test_constructs_two_clients_when_polish_enabled(
        self,
        runner: CliRunner,
        note_folder: Path,
        mocks: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_keys(monkeypatch)
        result = runner.invoke(notes_ocr_main, [str(note_folder)])
        assert result.exit_code == 0
        assert mocks["GeminiClient"].call_count == 2

    def test_empty_root_warns_and_exits_clean(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mocks: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_keys(monkeypatch)
        result = runner.invoke(notes_ocr_main, [str(tmp_path)])
        assert result.exit_code == 0
        assert mocks["process_folder_calls"] == []


class TestNoPolish:
    def test_polish_client_is_none(
        self,
        runner: CliRunner,
        note_folder: Path,
        mocks: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("NOTES_OCR_GEMINI_API_KEY", "ocr-key")
        monkeypatch.delenv("POLISH_GEMINI_API_KEY", raising=False)
        result = runner.invoke(notes_ocr_main, [str(note_folder), "--no-polish"])
        assert result.exit_code == 0
        kwargs = mocks["process_folder_calls"][0]["kwargs"]
        assert kwargs["polish_client"] is None

    def test_only_one_gemini_client_constructed(
        self,
        runner: CliRunner,
        note_folder: Path,
        mocks: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("NOTES_OCR_GEMINI_API_KEY", "ocr-key")
        monkeypatch.delenv("POLISH_GEMINI_API_KEY", raising=False)
        result = runner.invoke(notes_ocr_main, [str(note_folder), "--no-polish"])
        assert result.exit_code == 0
        assert mocks["GeminiClient"].call_count == 1


class TestJobsFlag:
    def test_explicit_jobs_forwarded(
        self,
        runner: CliRunner,
        note_folder: Path,
        mocks: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_keys(monkeypatch)
        result = runner.invoke(notes_ocr_main, [str(note_folder), "--jobs", "3"])
        assert result.exit_code == 0
        assert mocks["process_folder_calls"][0]["kwargs"]["jobs"] == 3

    def test_default_jobs_within_expected_range(
        self,
        runner: CliRunner,
        note_folder: Path,
        mocks: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_keys(monkeypatch)
        result = runner.invoke(notes_ocr_main, [str(note_folder)])
        assert result.exit_code == 0
        jobs = mocks["process_folder_calls"][0]["kwargs"]["jobs"]
        assert 1 <= jobs <= 8

    def test_zero_jobs_rejected(self, runner: CliRunner, note_folder: Path) -> None:
        result = runner.invoke(notes_ocr_main, [str(note_folder), "--jobs", "0"])
        assert result.exit_code != 0
