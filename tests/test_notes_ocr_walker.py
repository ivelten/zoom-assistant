"""Tests for zoom_assistant.notes_ocr.walker."""

from __future__ import annotations

from pathlib import Path

from zoom_assistant.notes_ocr.walker import NoteFolder, walk_note_folders


def _mkimg(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return path


def _names(folder: NoteFolder) -> list[str]:
    return [p.name for p in folder.images]


class TestFlatFolder:
    def test_empty_folder_yields_nothing(self, tmp_path: Path) -> None:
        assert list(walk_note_folders(tmp_path)) == []

    def test_single_image(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "a.png")
        folders = list(walk_note_folders(tmp_path))
        assert len(folders) == 1
        assert folders[0].path == tmp_path
        assert _names(folders[0]) == ["a.png"]

    def test_case_insensitive_extensions(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "a.PNG")
        _mkimg(tmp_path / "b.JPG")
        _mkimg(tmp_path / "c.Jpeg")
        folders = list(walk_note_folders(tmp_path))
        assert len(folders) == 1
        assert len(folders[0].images) == 3

    def test_non_image_files_ignored(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "a.png")
        (tmp_path / "README.txt").write_text("hi")
        folders = list(walk_note_folders(tmp_path))
        assert _names(folders[0]) == ["a.png"]


class TestImageLeafMerge:
    def test_parent_with_no_own_images_promoted_by_leaf_child(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "leaf" / "1.png")
        _mkimg(tmp_path / "leaf" / "2.png")
        folders = list(walk_note_folders(tmp_path))
        assert len(folders) == 1
        assert folders[0].path == tmp_path
        assert _names(folders[0]) == ["1.png", "2.png"]

    def test_image_leaf_does_not_get_own_note_folder(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "leaf" / "1.png")
        paths = {f.path for f in walk_note_folders(tmp_path)}
        assert tmp_path in paths
        assert tmp_path / "leaf" not in paths

    def test_multiple_leaves_merged(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "a" / "x.png")
        _mkimg(tmp_path / "b" / "y.png")
        folders = list(walk_note_folders(tmp_path))
        assert len(folders) == 1
        assert len(folders[0].images) == 2


class TestRecursion:
    def test_child_with_subdirs_is_not_image_leaf(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "sub" / "a.png")
        _mkimg(tmp_path / "sub" / "deeper" / "b.png")
        folders = list(walk_note_folders(tmp_path))
        assert len(folders) == 1
        assert folders[0].path == tmp_path / "sub"
        assert len(folders[0].images) == 2

    def test_independent_note_folders_at_different_depths(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "A" / "1.png")
        _mkimg(tmp_path / "B" / "x" / "1.png")
        _mkimg(tmp_path / "B" / "x" / "2.png")
        folders = list(walk_note_folders(tmp_path))
        paths = {f.path for f in folders}
        assert tmp_path in paths
        assert tmp_path / "B" in paths
        assert len(folders) == 2


class TestMergeOrder:
    def test_sorted_by_parent_then_filename(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        _mkimg(root / "own_z.png")
        _mkimg(root / "aleaf" / "y.png")
        _mkimg(root / "aleaf" / "a.png")
        _mkimg(root / "bleaf" / "b.png")
        folders = list(walk_note_folders(root))
        assert len(folders) == 1
        assert _names(folders[0]) == ["a.png", "y.png", "b.png", "own_z.png"]


class TestHiddenFiltering:
    def test_dotfiles_ignored(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / ".hidden.png")
        assert list(walk_note_folders(tmp_path)) == []

    def test_dotfolders_not_traversed(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / ".git" / "a.png")
        assert list(walk_note_folders(tmp_path)) == []
