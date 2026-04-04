"""Tests for edit_file (str_replace) operations."""

from pathlib import Path

import pytest

from memory_mcp import storage


class TestEditFileTree:
    def test_basic_replacement(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/notes.md", "# Notes\nOld content here")
        result = storage.edit_file(
            root, "projects/notes.md", "Old content", "New content"
        )
        assert result["path"] == "projects/notes.md"
        content = storage.read_file(root, "projects/notes.md")
        assert "New content here" in content
        assert "Old content" not in content

    def test_stamps_frontmatter(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/notes.md", "# Notes\nBody")
        storage.edit_file(root, "projects/notes.md", "Body", "Updated body")
        content = storage.read_file(root, "projects/notes.md")
        assert "updated:" in content

    def test_wikilinks_updated(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/notes.md", "# Notes\nSee [[old-link]]")
        storage.edit_file(root, "projects/notes.md", "[[old-link]]", "[[new-link]]")
        content = storage.read_file(root, "projects/notes.md")
        assert "new-link" in content

    def test_nested_file(self, root: Path) -> None:
        storage.create_directory(root, "projects/acme/")
        storage.write_tree_file(root, "projects/acme/notes.md", "# Notes\nContent")
        result = storage.edit_file(root, "projects/acme/notes.md", "Content", "Edited")
        assert result["path"] == "projects/acme/notes.md"

    def test_multiline_replacement(self, root: Path) -> None:
        storage.write_tree_file(
            root, "projects/notes.md", "# Notes\nLine 1\nLine 2\nLine 3"
        )
        storage.edit_file(
            root, "projects/notes.md", "Line 1\nLine 2", "Replaced 1\nReplaced 2"
        )
        content = storage.read_file(root, "projects/notes.md")
        assert "Replaced 1\nReplaced 2" in content
        assert "Line 3" in content


class TestEditFileFixed:
    def test_basic_replacement(self, root: Path) -> None:
        storage.update_fixed_page(root, "me/now.md", "# Now\nCurrent status")
        result = storage.edit_file(
            root, "me/now.md", "Current status", "Updated status"
        )
        assert result["path"] == "me/now.md"
        content = storage.read_file(root, "me/now.md")
        assert "Updated status" in content

    def test_rejects_invalid_page(self, root: Path) -> None:
        with pytest.raises(ValueError, match="Invalid page"):
            storage.edit_file(root, "me/invalid.md", "old", "new")


class TestEditFileLog:
    def test_basic_replacement(self, root: Path) -> None:
        entry = storage.add_log_entry(root, "daily", "## Morning\nDid stuff")
        result = storage.edit_file(root, entry["path"], "Did stuff", "Did things")
        assert result["path"] == entry["path"]
        content = storage.read_file(root, entry["path"])
        assert "Did things" in content
        assert "Did stuff" not in content


class TestEditFileErrors:
    def test_file_not_found(self, root: Path) -> None:
        with pytest.raises(ValueError, match="File not found"):
            storage.edit_file(root, "projects/nonexistent.md", "old", "new")

    def test_old_string_not_found(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/notes.md", "# Notes\nBody")
        with pytest.raises(ValueError, match="not found"):
            storage.edit_file(root, "projects/notes.md", "nonexistent text", "new")

    def test_multiple_matches(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/notes.md", "# Notes\nfoo bar foo")
        with pytest.raises(ValueError, match="matches 2 locations"):
            storage.edit_file(root, "projects/notes.md", "foo", "baz")

    def test_old_equals_new(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/notes.md", "# Notes\nBody")
        with pytest.raises(ValueError, match="identical"):
            storage.edit_file(root, "projects/notes.md", "Body", "Body")

    def test_empty_old_string(self, root: Path) -> None:
        storage.write_tree_file(root, "projects/notes.md", "# Notes\nBody")
        with pytest.raises(ValueError, match="must not be empty"):
            storage.edit_file(root, "projects/notes.md", "", "new")


class TestEditFilePreservation:
    def test_preserves_other_content(self, root: Path) -> None:
        storage.write_tree_file(
            root, "projects/notes.md", "# Title\nPara 1\n\nPara 2\n\nPara 3"
        )
        storage.edit_file(root, "projects/notes.md", "Para 2", "Edited para")
        content = storage.read_file(root, "projects/notes.md")
        assert "Para 1" in content
        assert "Edited para" in content
        assert "Para 3" in content

    def test_empty_new_string_deletes_text(self, root: Path) -> None:
        storage.write_tree_file(
            root, "projects/notes.md", "# Notes\nKeep this\nRemove this"
        )
        storage.edit_file(root, "projects/notes.md", "\nRemove this", "")
        content = storage.read_file(root, "projects/notes.md")
        assert "Remove this" not in content
        assert "Keep this" in content
