"""Tests for frontmatter utilities: _stamp_metadata, _extract_wikilinks."""

import frontmatter as fm

from memory_mcp.storage import (
    Behavior,
    DirConfig,
    _extract_wikilinks,
    _stamp_metadata,
)


class TestExtractWikilinks:
    def test_extracts_links(self) -> None:
        assert _extract_wikilinks("See [[foo]] and [[bar]]") == ["bar", "foo"]

    def test_deduplicates(self) -> None:
        assert _extract_wikilinks("[[a]] [[a]] [[b]]") == ["a", "b"]

    def test_no_links(self) -> None:
        assert _extract_wikilinks("no links here") == []

    def test_nested_brackets_ignored(self) -> None:
        assert _extract_wikilinks("[[valid]] [not[a]]link]]") == ["valid"]


class TestStampMetadata:
    def test_adds_updated_and_links(self) -> None:
        config = DirConfig(behavior=Behavior.TREE, description="test")
        result = _stamp_metadata("# Hello\n", config)
        post = fm.loads(result)
        assert "updated" in post.metadata
        assert "links" in post.metadata

    def test_adds_extra_frontmatter(self) -> None:
        config = DirConfig(
            behavior=Behavior.LOG,
            description="test",
            extra_frontmatter=("date",),
        )
        result = _stamp_metadata("# Log\n", config)
        post = fm.loads(result)
        assert "date" in post.metadata

    def test_preserves_existing_content(self) -> None:
        config = DirConfig(behavior=Behavior.TREE, description="test")
        result = _stamp_metadata("# Title\nBody text\n", config)
        assert "Body text" in result

    def test_extracts_wikilinks_into_links(self) -> None:
        config = DirConfig(behavior=Behavior.TREE, description="test")
        result = _stamp_metadata("See [[foo]] and [[bar]]\n", config)
        post = fm.loads(result)
        assert post.metadata["links"] == ["bar", "foo"]

    def test_date_not_overwritten_if_set(self) -> None:
        config = DirConfig(
            behavior=Behavior.LOG,
            description="test",
            extra_frontmatter=("date",),
        )
        input_text = "---\ndate: '2020-01-01'\n---\n# Log\n"
        result = _stamp_metadata(input_text, config)
        post = fm.loads(result)
        assert post.metadata["date"] == "2020-01-01"
