"""Tests for log-behavior section operations (add_log_entry, edit_log)."""

from pathlib import Path

import pytest

from memory_mcp import storage


class TestAddLogEntry:
    def test_creates_todays_log(self, root: Path) -> None:
        result = storage.add_log_entry(root, "daily", "## Morning\nDid stuff")
        assert result["path"].startswith("daily/")
        assert result["path"].endswith(".md")
        content = storage.read_file(root, result["path"])
        assert "Morning" in content

    def test_appends_to_existing_log(self, root: Path) -> None:
        result = storage.add_log_entry(root, "daily", "## First entry\n")
        storage.add_log_entry(root, "daily", "## Second entry\n")
        content = storage.read_file(root, result["path"])
        assert "First entry" in content
        assert "Second entry" in content

    def test_stamps_date_frontmatter(self, root: Path) -> None:
        result = storage.add_log_entry(root, "daily", "Hello")
        content = storage.read_file(root, result["path"])
        assert "date:" in content

    def test_rejects_wrong_behavior(self, root: Path) -> None:
        with pytest.raises(RuntimeError, match="bug in tool routing"):
            storage.add_log_entry(root, "projects", "content")

    def test_path_is_valid_memory_path(self, root: Path) -> None:
        result = storage.add_log_entry(root, "daily", "test")
        mp = storage.MemoryPath.parse(result["path"])
        assert mp.section == "daily"
        assert not mp.is_dir


class TestEditLog:
    def test_overwrites_content(self, root: Path) -> None:
        storage.add_log_entry(root, "daily", "old content")
        path = storage.add_log_entry(root, "daily", "")["path"]
        storage.edit_log(root, path, "# New content\nReplaced")
        content = storage.read_file(root, path)
        assert "New content" in content
        assert "old content" not in content

    def test_backfill_creates_file(self, root: Path) -> None:
        result = storage.edit_log(root, "daily/2000-01-01.md", "# Backfilled\nDid stuff")
        assert result["path"] == "daily/2000-01-01.md"
        content = storage.read_file(root, "daily/2000-01-01.md")
        assert "Backfilled" in content
        assert "date:" in content

    def test_rejects_wrong_behavior(self, root: Path) -> None:
        with pytest.raises(RuntimeError, match="bug in tool routing"):
            storage.edit_log(root, "me/now.md", "content")
