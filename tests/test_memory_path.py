"""Tests for MemoryPath: parse, __str__, __post_init__, resolve_file, resolve_dir."""

from pathlib import Path

import pytest

from memory_mcp.storage import MemoryPath


# --- parse() ---


class TestParse:
    def test_file_path(self) -> None:
        mp = MemoryPath.parse("me/now.md")
        assert mp.section == "me"
        assert mp.subpath == "now.md"
        assert mp.is_dir is False

    def test_nested_file_path(self) -> None:
        mp = MemoryPath.parse("projects/acme/notes.md")
        assert mp.section == "projects"
        assert mp.subpath == "acme/notes.md"
        assert mp.is_dir is False

    def test_section_dir(self) -> None:
        mp = MemoryPath.parse("projects/")
        assert mp.section == "projects"
        assert mp.subpath == ""
        assert mp.is_dir is True

    def test_nested_dir(self) -> None:
        mp = MemoryPath.parse("projects/acme/v2/")
        assert mp.section == "projects"
        assert mp.subpath == "acme/v2"
        assert mp.is_dir is True

    def test_trailing_slashes_collapsed(self) -> None:
        mp = MemoryPath.parse("projects///")
        assert mp.section == "projects"
        assert mp.subpath == ""
        assert mp.is_dir is True

    def test_rejects_bare_name(self) -> None:
        with pytest.raises(ValueError, match="must end with .md"):
            MemoryPath.parse("me")

    def test_rejects_no_suffix(self) -> None:
        with pytest.raises(ValueError, match="must end with .md"):
            MemoryPath.parse("projects/acme/notes")

    def test_rejects_unknown_section_file(self) -> None:
        with pytest.raises(ValueError, match="known section"):
            MemoryPath.parse("unknown/file.md")

    def test_rejects_unknown_section_dir(self) -> None:
        with pytest.raises(ValueError, match="known section"):
            MemoryPath.parse("unknown/")

    def test_rejects_no_slash_with_md(self) -> None:
        # "me.md" has no slash → section = "me.md" → unknown
        with pytest.raises(ValueError, match="known section"):
            MemoryPath.parse("me.md")


# --- __str__() ---


class TestStr:
    def test_file(self) -> None:
        assert str(MemoryPath("me", "now.md")) == "me/now.md"

    def test_nested_file(self) -> None:
        assert str(MemoryPath("projects", "acme/notes.md")) == "projects/acme/notes.md"

    def test_section_dir(self) -> None:
        assert str(MemoryPath("projects", "", is_dir=True)) == "projects/"

    def test_nested_dir(self) -> None:
        assert (
            str(MemoryPath("projects", "acme/v2", is_dir=True)) == "projects/acme/v2/"
        )


# --- __post_init__() ---


class TestPostInit:
    def test_rejects_dir_with_md_subpath(self) -> None:
        with pytest.raises(ValueError, match="Directory path has .md subpath"):
            MemoryPath("projects", "file.md", is_dir=True)

    def test_rejects_file_without_md_subpath(self) -> None:
        with pytest.raises(ValueError, match="File path must have .md subpath"):
            MemoryPath("projects", "acme")

    def test_allows_empty_subpath_for_dir(self) -> None:
        mp = MemoryPath("projects", "", is_dir=True)
        assert mp.is_dir is True


# --- ensure_file() / ensure_dir() ---


class TestEnsure:
    def test_ensure_file_passes(self) -> None:
        mp = MemoryPath("me", "now.md")
        assert mp.ensure_file() is mp

    def test_ensure_file_rejects_dir(self) -> None:
        mp = MemoryPath("projects", "", is_dir=True)
        with pytest.raises(ValueError, match="Expected a file path"):
            mp.ensure_file()

    def test_ensure_dir_passes(self) -> None:
        mp = MemoryPath("projects", "", is_dir=True)
        assert mp.ensure_dir() is mp

    def test_ensure_dir_rejects_file(self) -> None:
        mp = MemoryPath("me", "now.md")
        with pytest.raises(ValueError, match="Expected a directory path"):
            mp.ensure_dir()

    def test_chaining_with_parse(self) -> None:
        mp = MemoryPath.parse("projects/").ensure_dir()
        assert mp.is_dir is True
        mp = MemoryPath.parse("me/now.md").ensure_file()
        assert mp.is_dir is False


# --- parse_file() / parse_dir() ---


class TestParseFileDir:
    def test_parse_file(self) -> None:
        mp = MemoryPath.parse_file("me/now.md")
        assert mp.section == "me"
        assert mp.is_dir is False

    def test_parse_file_rejects_dir(self) -> None:
        with pytest.raises(ValueError, match="Expected a file path"):
            MemoryPath.parse_file("projects/")

    def test_parse_dir(self) -> None:
        mp = MemoryPath.parse_dir("projects/")
        assert mp.section == "projects"
        assert mp.is_dir is True

    def test_parse_dir_rejects_file(self) -> None:
        with pytest.raises(ValueError, match="Expected a directory path"):
            MemoryPath.parse_dir("me/now.md")


# --- resolve_file() / resolve_dir() ---


class TestResolve:
    def test_resolve_file(self, root: Path) -> None:
        mp = MemoryPath("me", "now.md")
        resolved = mp.resolve_file(root)
        assert resolved == (root / "me" / "now.md").resolve()

    def test_resolve_file_rejects_dir(self, root: Path) -> None:
        mp = MemoryPath("projects", "", is_dir=True)
        with pytest.raises(ValueError, match="Expected a file path"):
            mp.resolve_file(root)

    def test_resolve_dir(self, root: Path) -> None:
        mp = MemoryPath("projects", "", is_dir=True)
        resolved = mp.resolve_dir(root)
        assert resolved == (root / "projects").resolve()

    def test_resolve_dir_rejects_file(self, root: Path) -> None:
        mp = MemoryPath("me", "now.md")
        with pytest.raises(ValueError, match="Expected a directory path"):
            mp.resolve_dir(root)

    def test_path_traversal_blocked(self, root: Path) -> None:
        mp = MemoryPath("projects", "../../etc/passwd.md")
        with pytest.raises(ValueError, match="escapes memory directory"):
            mp.resolve_file(root)

    def test_resolve_file_through_symlink_outside_root(self, root: Path) -> None:
        external = root.parent / "external"
        external.mkdir()
        (external / "page.md").write_text("# Page\n")
        (root / "projects" / "linked").symlink_to(external)

        resolved = MemoryPath("projects", "linked/page.md").resolve_file(root)
        assert resolved.read_text() == "# Page\n"

    def test_resolve_dir_through_symlink_outside_root(self, root: Path) -> None:
        external = root.parent / "external_dir"
        external.mkdir()
        (root / "projects" / "linked").symlink_to(external)

        resolved = MemoryPath("projects", "linked", is_dir=True).resolve_dir(root)
        assert resolved.is_dir()


# --- roundtrip: parse() → str() ---


class TestRoundtrip:
    @pytest.mark.parametrize(
        "path",
        [
            "me/now.md",
            "projects/",
            "projects/acme/notes.md",
            "projects/acme/v2/",
            "daily/2026-03-18.md",
        ],
    )
    def test_roundtrip(self, path: str) -> None:
        assert str(MemoryPath.parse(path)) == path
