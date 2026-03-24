"""Tests for internal guard functions: _check_behavior, _check_parent_exists."""

from pathlib import Path

import pytest

from memory_mcp.storage import Behavior, _check_behavior, _check_parent_exists


class TestCheckBehavior:
    def test_returns_config_on_match(self) -> None:
        config = _check_behavior("me", Behavior.FIXED)
        assert config.behavior == Behavior.FIXED

    def test_raises_on_mismatch(self) -> None:
        with pytest.raises(RuntimeError, match="bug in tool routing"):
            _check_behavior("me", Behavior.TREE)

    def test_raises_on_unknown_section(self) -> None:
        with pytest.raises(RuntimeError, match="bug in tool routing"):
            _check_behavior("nonexistent", Behavior.TREE)


class TestCheckParentExists:
    def test_passes_when_parent_exists(self, root: Path) -> None:
        _check_parent_exists(root / "projects", "projects", root)

    def test_raises_when_missing(self, root: Path) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            _check_parent_exists(root / "projects" / "nope", "projects", root)

    def test_error_message_uses_memory_path(self, root: Path) -> None:
        with pytest.raises(ValueError, match="projects/nope/"):
            _check_parent_exists(root / "projects" / "nope", "projects", root)
