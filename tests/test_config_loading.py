"""Tests for section config loading: _parse_sections_json, load_sections, apply_sections."""

import json

import pytest

from memory_mcp.storage import (
    Behavior,
    DEFAULT_SECTIONS,
    DirConfig,
    _parse_sections_json,
    apply_sections,
    get_sections,
    load_sections,
)


class TestParseSectionsJson:
    def test_valid_tree_section(self) -> None:
        raw = json.dumps({"notes": {"behavior": "tree", "description": "My notes"}})
        result = _parse_sections_json(raw)
        assert "notes" in result
        assert result["notes"].behavior == Behavior.TREE

    def test_valid_fixed_section(self) -> None:
        raw = json.dumps(
            {
                "config": {
                    "behavior": "fixed",
                    "description": "Config files",
                    "valid_files": ["settings", "theme"],
                }
            }
        )
        result = _parse_sections_json(raw)
        assert result["config"].valid_files == frozenset({"settings", "theme"})

    def test_log_auto_adds_date(self) -> None:
        raw = json.dumps({"logs": {"behavior": "log", "description": "Logs"}})
        result = _parse_sections_json(raw)
        assert "date" in result["logs"].extra_frontmatter

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="not valid JSON"):
            _parse_sections_json("{bad json")

    def test_rejects_non_object(self) -> None:
        with pytest.raises(ValueError, match="must be a JSON object"):
            _parse_sections_json("[]")

    def test_rejects_invalid_name(self) -> None:
        raw = json.dumps({"bad-name": {"behavior": "tree", "description": "x"}})
        with pytest.raises(ValueError, match="valid identifier"):
            _parse_sections_json(raw)

    def test_rejects_override_default(self) -> None:
        raw = json.dumps({"me": {"behavior": "tree", "description": "x"}})
        with pytest.raises(ValueError, match="Cannot override default"):
            _parse_sections_json(raw)

    def test_rejects_missing_behavior(self) -> None:
        raw = json.dumps({"notes": {"description": "x"}})
        with pytest.raises(ValueError, match="behavior must be one of"):
            _parse_sections_json(raw)

    def test_rejects_missing_description(self) -> None:
        raw = json.dumps({"notes": {"behavior": "tree"}})
        with pytest.raises(ValueError, match="description is required"):
            _parse_sections_json(raw)

    def test_rejects_fixed_without_valid_files(self) -> None:
        raw = json.dumps({"cfg": {"behavior": "fixed", "description": "x"}})
        with pytest.raises(ValueError, match="requires valid_files"):
            _parse_sections_json(raw)

    def test_rejects_valid_files_with_slashes(self) -> None:
        raw = json.dumps(
            {
                "cfg": {
                    "behavior": "fixed",
                    "description": "x",
                    "valid_files": ["a/b"],
                }
            }
        )
        with pytest.raises(ValueError, match="simple name"):
            _parse_sections_json(raw)

    def test_rejects_unknown_extra_frontmatter(self) -> None:
        raw = json.dumps(
            {
                "notes": {
                    "behavior": "tree",
                    "description": "x",
                    "extra_frontmatter": ["unknown_field"],
                }
            }
        )
        with pytest.raises(ValueError, match="unknown extra_frontmatter"):
            _parse_sections_json(raw)


class TestLoadSections:
    def test_defaults_without_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MEMORY_SECTIONS", raising=False)
        result = load_sections()
        assert set(result.keys()) == set(DEFAULT_SECTIONS.keys())

    def test_merges_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        custom = json.dumps({"notes": {"behavior": "tree", "description": "Notes"}})
        monkeypatch.setenv("MEMORY_SECTIONS", custom)
        result = load_sections()
        assert "notes" in result
        assert "me" in result  # defaults preserved


class TestApplySections:
    def test_replaces_sections(self) -> None:
        saved = get_sections()
        try:
            custom = {"test": DirConfig(behavior=Behavior.TREE, description="test")}
            apply_sections(custom)
            current = get_sections()
            assert "test" in current
            assert "me" not in current
        finally:
            apply_sections(saved)
