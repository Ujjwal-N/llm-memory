"""Tests for init_memory_dir and _seed_file."""

from pathlib import Path

from memory_mcp import storage


class TestInitMemoryDir:
    def test_creates_all_section_dirs(self, root: Path) -> None:
        for name in storage.DEFAULT_SECTIONS:
            assert (root / name).is_dir()

    def test_seeds_fixed_pages(self, root: Path) -> None:
        config = storage.DEFAULT_SECTIONS["me"]
        assert config.valid_files is not None
        for page in config.valid_files:
            assert (root / "me" / f"{page}.md").is_file()

    def test_seeded_files_have_frontmatter(self, root: Path) -> None:
        content = (root / "me" / "now.md").read_text()
        assert "---" in content
        assert "updated:" in content

    def test_idempotent(self, root: Path) -> None:
        storage.init_memory_dir(root)
        result2 = storage.init_memory_dir(root)
        assert result2["created_directories"] == []
        assert result2["seeded_files"] == []

    def test_returns_created_info(self, tmp_path: Path) -> None:
        result = storage.init_memory_dir(tmp_path)
        assert "me" in result["created_directories"]
        assert any("me/" in f for f in result["seeded_files"])
