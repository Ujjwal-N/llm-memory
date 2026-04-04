"""Tests for internal guard functions: get_config, _check_behavior, _check_fixed_page, _check_parent_exists."""

from pathlib import Path

import pytest

from memory_mcp.storage import (
    Behavior,
    _check_behavior,
    _check_parent_exists,
    _check_fixed_page,
    get_config,
    MemoryPath,
)


class TestGetConfig:
    def test_returns_config(self) -> None:
        config = get_config("me")
        assert config.behavior == Behavior.FIXED

    def test_raises_on_unknown_section(self) -> None:
        with pytest.raises(ValueError, match="Unknown section"):
            get_config("nonexistent")


class TestCheckBehavior:
    def test_returns_config_on_match(self) -> None:
        config = _check_behavior("me", Behavior.FIXED)
        assert config.behavior == Behavior.FIXED

    def test_raises_on_mismatch(self) -> None:
        with pytest.raises(ValueError, match="requires a tree section"):
            _check_behavior("me", Behavior.TREE)

    def test_raises_on_unknown_section(self) -> None:
        with pytest.raises(ValueError, match="Unknown section"):
            _check_behavior("nonexistent", Behavior.TREE)


class TestCheckValidPage:
    def test_passes_valid_page(self) -> None:
        config = get_config("me")
        mp = MemoryPath.parse_file("me/now.md")
        _check_fixed_page(mp, config)

    def test_rejects_invalid_page(self) -> None:
        config = get_config("me")
        mp = MemoryPath.parse_file("me/invalid.md")
        with pytest.raises(ValueError, match="Invalid page"):
            _check_fixed_page(mp, config)

    def test_noop_for_tree(self) -> None:
        config = get_config("projects")
        mp = MemoryPath.parse_file("projects/anything.md")
        _check_fixed_page(mp, config)


class TestCheckParentExists:
    def test_passes_when_parent_exists(self, root: Path) -> None:
        _check_parent_exists(root / "projects", "projects", root)

    def test_raises_when_missing(self, root: Path) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            _check_parent_exists(root / "projects" / "nope", "projects", root)

    def test_error_message_uses_memory_path(self, root: Path) -> None:
        with pytest.raises(ValueError, match="projects/nope/"):
            _check_parent_exists(root / "projects" / "nope", "projects", root)
