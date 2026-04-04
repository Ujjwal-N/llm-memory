"""Integration tests for the MCP server tools via FastMCP Client."""

from pathlib import Path

import pytest
from fastmcp import Client

from memory_mcp import storage
from memory_mcp.server import mcp


@pytest.fixture()
def _server_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point MEMORY_DIR at a temp dir and initialize it."""
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    saved = storage.get_sections()
    storage.apply_sections(dict(storage.DEFAULT_SECTIONS))
    storage.init_memory_dir(tmp_path)
    yield tmp_path
    storage.apply_sections(saved)


async def _call(client: Client, tool: str, **kwargs: object) -> object:
    result = await client.call_tool(tool, kwargs)
    if isinstance(result, list) and len(result) == 1:
        return result[0].data
    return result


async def _call_expect_error(client: Client, tool: str, **kwargs: object) -> str:
    result = await client.call_tool(tool, kwargs, raise_on_error=False)
    if isinstance(result, list):
        assert result[0].is_error
        return str(result[0].data)
    assert result.is_error
    return str(result)


class TestServerTools:
    async def test_list_tools(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools}
            expected = {
                "scan_schema",
                "read_file",
                "write_file",
                "edit_file",
                "create_directory",
                "move_file",
                "delete_file",
                "add_log_entry",
            }
            assert names == expected

    async def test_scan_schema_full(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            result = await _call(client, "scan_schema")
            assert "me" in str(result)

    async def test_scan_schema_scoped(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            result = await _call(client, "scan_schema", path="me/")
            assert "me/" in str(result)

    async def test_read_file(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            result = await _call(client, "read_file", path="me/now.md")
            assert "# Now" in str(result)

    async def test_read_file_not_found(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            err = await _call_expect_error(client, "read_file", path="projects/nope.md")
            assert "not found" in err.lower()

    async def test_write_file_fixed(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            result = await _call(
                client, "write_file", path="me/now.md", content="# Now\nUpdated"
            )
            assert "me/now.md" in str(result)

    async def test_write_file_tree(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            result = await _call(
                client,
                "write_file",
                path="projects/notes.md",
                content="# Notes",
            )
            assert "notes.md" in str(result)

    async def test_write_file_log(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            result = await _call(
                client,
                "write_file",
                path="daily/2026-01-01.md",
                content="# Backfilled",
            )
            assert "daily/2026-01-01.md" in str(result)

    async def test_write_file_rejects_dir_path(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            err = await _call_expect_error(
                client, "write_file", path="projects/", content="x"
            )
            assert "file path" in err.lower()

    async def test_create_directory(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            result = await _call(client, "create_directory", path="projects/acme/")
            assert "acme" in str(result)
            assert (_server_root / "projects" / "acme").is_dir()

    async def test_move_file(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            await _call(
                client,
                "write_file",
                path="projects/old.md",
                content="# Old",
            )
            result = await _call(
                client,
                "move_file",
                source="projects/old.md",
                destination="projects/new.md",
            )
            assert "new.md" in str(result)

    async def test_delete_file(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            await _call(
                client,
                "write_file",
                path="projects/temp.md",
                content="# Temp",
            )
            result = await _call(client, "delete_file", path="projects/temp.md")
            assert "temp.md" in str(result)

    async def test_delete_file_rejects_fixed(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            err = await _call_expect_error(client, "delete_file", path="me/now.md")
            assert "fixed" in err.lower()

    async def test_add_log_entry(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            result = await _call(
                client, "add_log_entry", section="daily", content="## Morning\n"
            )
            assert "daily/" in str(result)
            assert ".md" in str(result)

    async def test_edit_file_tree(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            await _call(
                client,
                "write_file",
                path="projects/notes.md",
                content="# Notes\nOriginal content",
            )
            result = await _call(
                client,
                "edit_file",
                path="projects/notes.md",
                old_string="Original content",
                new_string="Edited content",
            )
            assert "notes.md" in str(result)

    async def test_edit_file_fixed(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            await _call(
                client, "write_file", path="me/now.md", content="# Now\nCurrent"
            )
            result = await _call(
                client,
                "edit_file",
                path="me/now.md",
                old_string="Current",
                new_string="Updated",
            )
            assert "me/now.md" in str(result)

    async def test_edit_file_not_found(self, _server_root: Path) -> None:
        async with Client(mcp) as client:
            err = await _call_expect_error(
                client,
                "edit_file",
                path="projects/nope.md",
                old_string="x",
                new_string="y",
            )
            assert "not found" in err.lower()

    async def test_behavior_mismatch_error(self, _server_root: Path) -> None:
        """Wrong section type gives actionable error (e.g. create_directory on fixed)."""
        async with Client(mcp) as client:
            err = await _call_expect_error(
                client, "create_directory", path="me/subdir/"
            )
            assert "requires a tree section" in err.lower()

    async def test_instructions_content(self) -> None:
        from memory_mcp.server import INSTRUCTIONS

        assert "me/" in INSTRUCTIONS
        assert "daily/" in INSTRUCTIONS
        assert "projects/" in INSTRUCTIONS
        assert ".md" in INSTRUCTIONS
