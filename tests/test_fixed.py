"""Tests for fixed-behavior section operations (update_fixed_page)."""

from pathlib import Path

import pytest

from memory_mcp import storage


class TestUpdateFixedPage:
    def test_updates_valid_page(self, root: Path) -> None:
        result = storage.update_fixed_page(root, "me/now.md", "# Now\nUpdated content")
        assert result["path"] == "me/now.md"
        content = storage.read_file(root, "me/now.md")
        assert "Updated content" in content

    def test_stamps_frontmatter(self, root: Path) -> None:
        storage.update_fixed_page(root, "me/now.md", "# Now\nHello")
        content = storage.read_file(root, "me/now.md")
        assert "updated:" in content
        assert "links:" in content

    def test_rejects_invalid_page(self, root: Path) -> None:
        with pytest.raises(ValueError, match="Invalid page"):
            storage.update_fixed_page(root, "me/invalid.md", "content")

    def test_rejects_wrong_behavior(self, root: Path) -> None:
        with pytest.raises(RuntimeError, match="bug in tool routing"):
            storage.update_fixed_page(root, "projects/file.md", "content")

    def test_wikilinks_extracted(self, root: Path) -> None:
        storage.update_fixed_page(
            root, "me/now.md", "# Now\nSee [[goals]] and [[about]]"
        )
        content = storage.read_file(root, "me/now.md")
        assert "about" in content
        assert "goals" in content
