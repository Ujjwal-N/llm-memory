"""Tests for read_file, scan_schema, and internal scan helpers."""

from pathlib import Path

import pytest

from memory_mcp import storage


class TestReadFile:
    def test_reads_seeded_file(self, root: Path) -> None:
        content = storage.read_file(root, "me/now.md")
        assert "# Now" in content

    def test_not_found(self, root: Path) -> None:
        with pytest.raises(ValueError, match="File not found"):
            storage.read_file(root, "projects/nope.md")

    def test_rejects_directory_path(self, root: Path) -> None:
        with pytest.raises(ValueError, match="Expected a file path"):
            storage.read_file(root, "projects/")


class TestScanSchemaFull:
    def test_returns_all_sections(self, root: Path) -> None:
        result = storage.scan_schema(root)
        for name in storage.DEFAULT_SECTIONS:
            assert f"{name}/" in result

    def test_fixed_files_have_md_paths(self, root: Path) -> None:
        result = storage.scan_schema(root)
        for entry in result["me/"]:
            assert entry["path"].endswith(".md")
            assert "modified" in entry

    def test_empty_tree_section(self, root: Path) -> None:
        result = storage.scan_schema(root)
        assert result["projects/"] == []

    def test_empty_log_section(self, root: Path) -> None:
        result = storage.scan_schema(root)
        assert result["daily/"] == []


class TestScanSchemaScoped:
    def test_scoped_section(self, root: Path) -> None:
        result = storage.scan_schema(root, "me/")
        assert result["path"] == "me/"
        assert "entries" in result

    def test_scoped_subdir(self, root: Path) -> None:
        storage.create_directory(root, "projects/acme/")
        storage.write_tree_file(root, "projects/acme/notes.md", "# Notes")
        result = storage.scan_schema(root, "projects/acme/")
        assert result["path"] == "projects/acme/"
        assert "tree" in result
        paths = [e["path"] for e in result["tree"]]
        assert "projects/acme/notes.md" in paths

    def test_rejects_file_path(self, root: Path) -> None:
        with pytest.raises(ValueError, match="directory path"):
            storage.scan_schema(root, "me/now.md")

    def test_nonexistent_subdir(self, root: Path) -> None:
        with pytest.raises(ValueError, match="Not a directory"):
            storage.scan_schema(root, "projects/nope/")


class TestScanTree:
    def test_nested_structure(self, root: Path) -> None:
        storage.create_directory(root, "projects/acme/")
        storage.create_directory(root, "projects/acme/docs/")
        storage.write_tree_file(root, "projects/acme/notes.md", "# Notes")
        storage.write_tree_file(root, "projects/acme/docs/readme.md", "# Readme")

        result = storage.scan_schema(root, "projects/")
        entries = result["entries"]
        acme = next(e for e in entries if e["path"] == "projects/acme/")
        assert "children" in acme

        child_paths = [c["path"] for c in acme["children"]]
        assert "projects/acme/docs/" in child_paths
        assert "projects/acme/notes.md" in child_paths

    def test_skips_dotfiles(self, root: Path) -> None:
        (root / "projects" / ".hidden").touch()
        result = storage.scan_schema(root, "projects/")
        paths = [e["path"] for e in result["entries"]]
        assert not any(".hidden" in p for p in paths)
