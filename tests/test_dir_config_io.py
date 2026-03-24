"""Tests for read_dir_config and write_dir_config."""

from pathlib import Path

from memory_mcp.storage import (
    Behavior,
    DirConfig,
    read_dir_config,
    write_dir_config,
)


class TestReadDirConfig:
    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        assert read_dir_config(tmp_path / "_index.md") is None

    def test_returns_none_without_behavior(self, tmp_path: Path) -> None:
        index = tmp_path / "_index.md"
        index.write_text("---\ndescription: just content\n---\n# Hello\n")
        assert read_dir_config(index) is None

    def test_reads_full_config(self, tmp_path: Path) -> None:
        index = tmp_path / "_index.md"
        index.write_text(
            "---\n"
            "behavior: log\n"
            "description: Daily logs\n"
            "extra_frontmatter:\n  - date\n"
            "---\n# Logs\n"
        )
        config = read_dir_config(index)
        assert config is not None
        assert config.behavior == Behavior.LOG
        assert config.description == "Daily logs"
        assert config.extra_frontmatter == ("date",)

    def test_reads_valid_files(self, tmp_path: Path) -> None:
        index = tmp_path / "_index.md"
        index.write_text(
            "---\n"
            "behavior: fixed\n"
            "description: Fixed pages\n"
            "valid_files:\n  - config\n  - setup\n"
            "---\n"
        )
        config = read_dir_config(index)
        assert config is not None
        assert config.valid_files == frozenset({"config", "setup"})

    def test_ignores_invalid_behavior(self, tmp_path: Path) -> None:
        index = tmp_path / "_index.md"
        index.write_text("---\nbehavior: invalid\n---\n")
        assert read_dir_config(index) is None


class TestWriteDirConfig:
    def test_writes_config(self, tmp_path: Path) -> None:
        index = tmp_path / "_index.md"
        config = DirConfig(
            behavior=Behavior.TREE,
            description="Project files",
        )
        write_dir_config(index, config, "# Projects\n")
        result = read_dir_config(index)
        assert result is not None
        assert result.behavior == Behavior.TREE
        assert result.description == "Project files"

    def test_roundtrip_with_extras(self, tmp_path: Path) -> None:
        index = tmp_path / "_index.md"
        config = DirConfig(
            behavior=Behavior.LOG,
            description="Logs",
            extra_frontmatter=("date",),
        )
        write_dir_config(index, config, "# Logs\n")
        result = read_dir_config(index)
        assert result is not None
        assert result.extra_frontmatter == ("date",)

    def test_roundtrip_with_valid_files(self, tmp_path: Path) -> None:
        index = tmp_path / "_index.md"
        config = DirConfig(
            behavior=Behavior.FIXED,
            description="Fixed",
            valid_files=frozenset({"a", "b"}),
        )
        write_dir_config(index, config, "# Fixed\n")
        result = read_dir_config(index)
        assert result is not None
        assert result.valid_files == frozenset({"a", "b"})

    def test_preserves_body_content(self, tmp_path: Path) -> None:
        index = tmp_path / "_index.md"
        config = DirConfig(behavior=Behavior.TREE, description="test")
        write_dir_config(index, config, "# Title\nBody text here\n")
        content = index.read_text()
        assert "Body text here" in content
