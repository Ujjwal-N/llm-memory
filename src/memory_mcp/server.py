"""FastMCP server: instructions, tools, resources, and prompts for the memory layer."""

import functools
from collections.abc import Callable
from typing import TypeVar

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from memory_mcp import storage

_T = TypeVar("_T")

_APPLICABLE_TOOLS: dict[storage.Behavior, list[str]] = {
    storage.Behavior.FIXED: [
        "read_file",
        "write_file",
        "scan_schema",
        "describe_section",
    ],
    storage.Behavior.LOG: [
        "read_file",
        "add_log_entry",
        "edit_log",
        "delete_file",
        "scan_schema",
        "describe_section",
    ],
    storage.Behavior.TREE: [
        "read_file",
        "write_file",
        "create_directory",
        "move_file",
        "delete_file",
        "scan_schema",
        "describe_section",
    ],
}


def _tool_errors(fn: Callable[..., _T]) -> Callable[..., _T]:
    """Convert storage ValueError to ToolError (sets isError=true in MCP response)."""

    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> _T:
        try:
            return fn(*args, **kwargs)
        except ValueError as e:
            raise ToolError(str(e)) from e

    return wrapper


# --- Config loading (before tool registration) ---

_sections = storage.load_sections()
storage.apply_sections(_sections)


def _build_instructions() -> str:
    """Generate INSTRUCTIONS from SectionConfig descriptions."""
    section_lines: list[str] = []
    for name, cfg in _sections.items():
        section_lines.append(f"- {name}/ ({cfg.behavior})")
    sections_block = "\n".join(section_lines)

    return f"""\
You are connected to a personal memory layer stored as markdown files.

PATHS: All paths use the format "section/subpath" (e.g. "me/now", "daily/2026-03-18", \
"projects/demo/notes"). This format is used everywhere — tool inputs, return values, \
scan_schema output, and read_file. Paths from one tool can be passed directly to another.

WORKFLOWS:
- Before writing to a section for the first time: call describe_section to learn its \
rules and applicable tools.
- After any structural change (file creates, moves, deletes): call scan_schema to \
refresh your map.

SECTIONS:
{sections_block}\
"""


INSTRUCTIONS = _build_instructions()

mcp = FastMCP("memory", instructions=INSTRUCTIONS)


# --- Tools ---


@mcp.tool(
    annotations=ToolAnnotations(
        title="Scan Memory Structure",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
@_tool_errors
def scan_schema(path: str | None = None) -> dict:
    """Scan the memory directory and return a structured schema of all files.

    Each file entry has a path (usable with read_file) and a modified timestamp.
    Tree sections also include type and nested children.

    Use at session start to understand the full directory layout. Call again
    after any structural changes.

    Args:
        path: Optional subdirectory to scope the scan (e.g. "projects/acme").
              Omit to scan the entire memory directory.

    Returns:
        Full scan: {me: [...], daily: [...], projects: <tree>, ...}
        Scoped scan: {path: str, tree: [...]}
    """
    return storage.scan_schema(storage.get_root(), path)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Describe Section",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
@_tool_errors
def describe_section(section: str | None = None) -> list[dict] | dict:
    """Get info about a memory section before using it.

    Call with no argument to list all sections.
    Call with a section name to get its details and applicable tools.

    Args:
        section: Section name (e.g. "me", "daily", "projects"). Omit for all.

    Returns:
        Each entry: {name, behavior, description, applicable_tools, valid_files?}
    """
    result = storage.describe_section(section)

    def _enrich(guide: dict) -> dict:
        behavior = storage.Behavior(guide["behavior"])
        guide["applicable_tools"] = _APPLICABLE_TOOLS[behavior]
        return guide

    if isinstance(result, list):
        return [_enrich(g) for g in result]
    return _enrich(result)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Read File",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
@_tool_errors
def read_file(path: str) -> str:
    """Read a file by path (without .md extension).

    Works for any section. For directories, reads the _index.md within.

    Args:
        path: Full path (e.g. "me/now", "daily/2026-03-18", "projects/acme/notes").

    Returns:
        The full file content (including frontmatter) as a string.
    """
    return storage.read_file(storage.get_root(), path)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Write File",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
@_tool_errors
def write_file(path: str, content: str) -> dict:
    """Create or overwrite a file. Works for tree and fixed sections.

    This OVERWRITES the entire file. To preserve existing content, read the file
    first, merge changes, then write back. Frontmatter is auto-stamped.

    For fixed sections (me/): only valid pages can be written.
    For tree sections (projects/): parent directory must already exist.

    Args:
        path: Full path (e.g. "me/now", "projects/acme/notes").
        content: The complete file content to write.

    Returns:
        {path, full_content}
    """
    mp = storage.MemoryPath.parse(path)
    config = storage._sections[mp.section]
    if config.behavior == storage.Behavior.FIXED:
        return storage.update_fixed_page(storage.get_root(), path, content)
    if config.behavior == storage.Behavior.TREE:
        return storage.write_tree_file(storage.get_root(), path, content)
    raise ToolError(
        f"Cannot write directly to '{mp.section}/' (log section). "
        f"Use add_log_entry to append or edit_log to overwrite."
    )


@mcp.tool(
    annotations=ToolAnnotations(
        title="Create Directory",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )
)
@_tool_errors
def create_directory(path: str) -> dict:
    """Create a directory in a tree section.

    Only creates one level — parent directory must already exist.
    Build nested structures one level at a time.

    Args:
        path: Full path (e.g. "projects/acme" or "projects/acme/v2").

    Returns:
        {path}
    """
    return storage.create_directory(storage.get_root(), path)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Move File",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )
)
@_tool_errors
def move_file(source: str, destination: str) -> dict:
    """Move or rename a file within a tree section.

    Destination directory must already exist. Does NOT update [[wikilinks]]
    in other files — read affected files and update references manually.

    Args:
        source: Full path (e.g. "projects/acme/old-name").
        destination: Full path (e.g. "projects/acme/new-name").

    Returns:
        {path, full_content}
    """
    return storage.move_tree_file(storage.get_root(), source, destination)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Delete File",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    )
)
@_tool_errors
def delete_file(path: str) -> dict:
    """Delete a file in any non-fixed section (tree or log).

    Cleans up empty parent directories after deletion.

    Args:
        path: Full path (e.g. "projects/acme/old-notes", "daily/2026-03-18").

    Returns:
        {path}
    """
    return storage.delete_file(storage.get_root(), path)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Add Log Entry",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )
)
@_tool_errors
def add_log_entry(section: str, content: str) -> dict:
    """Append an entry to today's log in a log section.

    Creates today's log file if it doesn't exist. Content is appended as-is —
    structure the entry however you want (headings, lists, prose).

    Args:
        section: Section name (e.g. "daily").
        content: The content to append.

    Returns:
        {path, full_content}
    """
    return storage.add_log_entry(storage.get_root(), section, content)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Edit Log",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
@_tool_errors
def edit_log(path: str, content: str) -> dict:
    """Overwrite the full content of a log entry for corrections.

    Read the log first, make your changes, then write back the complete content.
    Only use this to correct or reorganize existing entries — use add_log_entry
    for new entries.

    Args:
        path: Full path (e.g. "daily/2026-03-18").
        content: The complete file content.

    Returns:
        {path, full_content}
    """
    return storage.edit_log(storage.get_root(), path, content)


if __name__ == "__main__":
    mcp.run()
