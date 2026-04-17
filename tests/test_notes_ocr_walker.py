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

    def test_multiple_images_sorted_by_filename(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "b.png")
        _mkimg(tmp_path / "a.png")
        _mkimg(tmp_path / "c.jpg")
        folders = list(walk_note_folders(tmp_path))
        assert _names(folders[0]) == ["a.png", "b.png", "c.jpg"]

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


class TestPerSubfolderOutput:
    def test_each_subfolder_gets_its_own_note_folder(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "a" / "1.png")
        _mkimg(tmp_path / "b" / "1.png")
        folders = list(walk_note_folders(tmp_path))
        paths = {f.path for f in folders}
        assert paths == {tmp_path / "a", tmp_path / "b"}

    def test_parent_without_own_images_is_not_a_note_folder(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "only_in_child" / "x.png")
        folders = list(walk_note_folders(tmp_path))
        paths = {f.path for f in folders}
        assert tmp_path not in paths
        assert tmp_path / "only_in_child" in paths

    def test_parent_with_own_images_does_not_absorb_subfolder_images(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "parent.png")
        _mkimg(tmp_path / "child" / "sub.png")
        folders = {f.path: f for f in walk_note_folders(tmp_path)}
        assert set(folders) == {tmp_path, tmp_path / "child"}
        assert _names(folders[tmp_path]) == ["parent.png"]
        assert _names(folders[tmp_path / "child"]) == ["sub.png"]

    def test_deep_nesting_yields_every_image_bearing_folder(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "a.png")
        _mkimg(tmp_path / "sub" / "b.png")
        _mkimg(tmp_path / "sub" / "deeper" / "c.png")
        paths = {f.path for f in walk_note_folders(tmp_path)}
        assert paths == {
            tmp_path,
            tmp_path / "sub",
            tmp_path / "sub" / "deeper",
        }


class TestSiblingOrder:
    def test_sibling_folders_walked_sorted(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / "z" / "1.png")
        _mkimg(tmp_path / "a" / "1.png")
        _mkimg(tmp_path / "m" / "1.png")
        discovered = [f.path.name for f in walk_note_folders(tmp_path)]
        assert discovered == ["a", "m", "z"]


class TestHiddenFiltering:
    def test_dotfiles_ignored(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / ".hidden.png")
        assert list(walk_note_folders(tmp_path)) == []

    def test_dotfolders_not_traversed(self, tmp_path: Path) -> None:
        _mkimg(tmp_path / ".git" / "a.png")
        assert list(walk_note_folders(tmp_path)) == []
