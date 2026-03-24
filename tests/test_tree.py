"""Tests for tree-behavior section operations (create_directory, write_tree_file, move_tree_file, delete_file)."""

from pathlib import Path

import pytest

from memory_mcp import storage


class TestCreateDirectory:
    def test_creates_dir(self, root: Path) -> None:
        result = storage.create_directory(root, "projects/acme/")
        assert result["path"] == "projects/acme/"
        assert (root / "projects" / "acme").is_dir()

    def test_already_exists(self, root: Path) -> None:
        storage.create_directory(root, "projects/acme/")
        with pytest.raises(ValueError, match="already exists"):
            storage.create_directory(root, "projects/acme/")

    def test_parent_must_exist(self, root: Path) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            storage.create_directory(root, "projects/acme/deep/")

    def test_rejects_non_tree(self, root: Path) -> None:
        with pytest.raises(RuntimeError, match="bug in tool routing"):
            storage.create_directory(root, "me/subdir/")

    def test_rejects_file_path(self, root: Path) -> None:
        with pytest.raises(ValueError, match="Expected a directory path"):
            # MemoryPath.parse will return a file mp, then resolve_dir rejects
            storage.create_directory(root, "projects/acme.md")


class TestWriteTreeFile:
    def test_creates_file(self, root: Path) -> None:
        result = storage.write_tree_file(root, "projects/notes.md", "# Notes")
        assert result["path"] == "projects/notes.md"
        assert (root / "projects" / "notes.md").is_file()

    def test_stamps_frontmatter(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/notes.md", "# Notes")
        content = storage.read_file(root, "projects/notes.md")
        assert "updated:" in content

    def test_overwrites_existing(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/notes.md", "# Old")
        storage.write_tree_file(root, "projects/notes.md", "# New")
        content = storage.read_file(root, "projects/notes.md")
        assert "New" in content
        assert "Old" not in content

    def test_parent_must_exist(self, root: Path) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            storage.write_tree_file(root, "projects/acme/notes.md", "content")

    def test_nested_file(self, root: Path) -> None:
        storage.create_directory(root, "projects/acme/")
        result = storage.write_tree_file(root, "projects/acme/notes.md", "# Notes")
        assert result["path"] == "projects/acme/notes.md"


class TestMoveTreeFile:
    def test_moves_file(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/old.md", "# Content")
        result = storage.move_tree_file(root, "projects/old.md", "projects/new.md")
        assert result["path"] == "projects/new.md"
        assert not (root / "projects" / "old.md").exists()
        content = storage.read_file(root, "projects/new.md")
        assert "Content" in content

    def test_source_not_found(self, root: Path) -> None:
        with pytest.raises(ValueError, match="Source not found"):
            storage.move_tree_file(root, "projects/nope.md", "projects/new.md")

    def test_destination_exists(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/a.md", "A")
        storage.write_tree_file(root, "projects/b.md", "B")
        with pytest.raises(ValueError, match="Destination already exists"):
            storage.move_tree_file(root, "projects/a.md", "projects/b.md")

    def test_destination_parent_must_exist(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/a.md", "A")
        with pytest.raises(ValueError, match="does not exist"):
            storage.move_tree_file(root, "projects/a.md", "projects/deep/a.md")

    def test_rejects_move_into_non_tree(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/a.md", "A")
        with pytest.raises(ValueError, match="only tree sections"):
            storage.move_tree_file(root, "projects/a.md", "daily/a.md")

    def test_move_across_dirs(self, root: Path) -> None:
        storage.create_directory(root, "projects/src/")
        storage.create_directory(root, "projects/dst/")
        storage.write_tree_file(root, "projects/src/file.md", "# Content")
        result = storage.move_tree_file(
            root, "projects/src/file.md", "projects/dst/file.md"
        )
        assert result["path"] == "projects/dst/file.md"


class TestDeleteFile:
    def test_deletes_tree_file(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/notes.md", "# Notes")
        result = storage.delete_file(root, "projects/notes.md")
        assert result["path"] == "projects/notes.md"
        assert not (root / "projects" / "notes.md").exists()

    def test_deletes_log_file(self, root: Path) -> None:
        entry = storage.add_log_entry(root, "daily", "content")
        result = storage.delete_file(root, entry["path"])
        assert result["path"] == entry["path"]

    def test_rejects_fixed_section(self, root: Path) -> None:
        with pytest.raises(ValueError, match="fixed section"):
            storage.delete_file(root, "me/now.md")

    def test_not_found(self, root: Path) -> None:
        with pytest.raises(ValueError, match="File not found"):
            storage.delete_file(root, "projects/nope.md")

    def test_cleans_up_empty_parents(self, root: Path) -> None:
        storage.create_directory(root, "projects/acme/")
        storage.write_tree_file(root, "projects/acme/notes.md", "content")
        storage.delete_file(root, "projects/acme/notes.md")
        assert not (root / "projects" / "acme").exists()

    def test_does_not_clean_section_dir(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/notes.md", "content")
        storage.delete_file(root, "projects/notes.md")
        assert (root / "projects").is_dir()

    def test_index_md_blocked_if_siblings(self, root: Path) -> None:
        storage.create_directory(root, "projects/acme/")
        storage.write_tree_file(root, "projects/acme/notes.md", "content")
        (root / "projects" / "acme" / "_index.md").write_text("# Index")
        with pytest.raises(ValueError, match="Cannot delete _index.md"):
            storage.delete_file(root, "projects/acme/_index.md")

    def test_index_md_allowed_if_alone(self, root: Path) -> None:
        storage.create_directory(root, "projects/acme/")
        (root / "projects" / "acme" / "_index.md").write_text("# Index")
        storage.delete_file(root, "projects/acme/_index.md")
        assert not (root / "projects" / "acme" / "_index.md").exists()
