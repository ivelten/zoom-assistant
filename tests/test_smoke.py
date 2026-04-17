"""Smoke test — Phase 1 scaffolding installs and imports cleanly."""

from __future__ import annotations


def test_package_importable() -> None:
    import zoom_assistant

    assert zoom_assistant is not None


def test_cli_entry_points_resolvable() -> None:
    from zoom_assistant.cli import notes_ocr_main, zoom_notes_main

    assert callable(notes_ocr_main)
    assert callable(zoom_notes_main)
