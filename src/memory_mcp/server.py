"""FastMCP server: instructions and tools for the memory layer."""

import functools
from collections.abc import Callable
from typing import TypeVar

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from memory_mcp import storage
from memory_mcp.storage import PathResult

_T = TypeVar("_T")


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

_configs = storage.load_sections()
storage.apply_sections(_configs)


def _build_instructions() -> str:
    """Generate INSTRUCTIONS from DirConfig descriptions."""
    section_lines: list[str] = []
    for name, cfg in _configs.items():
        line = f"- {name}/ ({cfg.behavior}): {cfg.description}"
        if cfg.valid_files:
            valid = ", ".join(
                str(storage.MemoryPath(name, f"{f}.md"))
                for f in sorted(cfg.valid_files)
            )
            line += f" Valid files: {valid}."
        section_lines.append(line)
    sections_block = "\n".join(section_lines)

    return f"""\
You are connected to a personal memory layer stored as markdown files.

PATHS: File paths end with .md, directory paths end with /. \
Paths without .md or / are rejected. \
Paths from one tool's output compose directly into another tool's input. \
scan_schema and create_directory take directory paths (/). All other tools take file paths (.md).

BEHAVIORS:
- fixed: read + write only. Files are predefined, cannot create/delete/move.
- log: append today via add_log_entry, correct or backfill via edit_log. Can delete. Cannot move.
- tree: full control. read, write, create_directory, move, delete.

SECTIONS:
{sections_block}

After any structural change, call scan_schema to refresh your map.\
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
    """Scan the memory directory and return a structured schema.

    File entries: {path (ends with .md), modified}.
    Directory entries: {path (ends with /), children}.
    Path suffixes are self-describing: .md = file, / = directory.

    Use at session start to understand the full directory layout. Call again
    after any structural changes.

    Args:
        path: Optional directory path to scope the scan (must end with /).
              Examples: "projects/", "projects/acme/". Omit to scan everything.

    Returns:
        Full scan: {"me/": [...], "daily/": [...], "projects/": [...]}
        Scoped scan: {path, entries: [...]} or {path, children: [...]}
    """
    return storage.scan_schema(storage.get_root(), path)


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
    """Read a markdown file by path.

    Works for any section. Path must end with .md.

    Args:
        path: File path (e.g. "me/now.md", "daily/2026-03-18.md", "projects/acme/notes.md").

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
def write_file(path: str, content: str) -> PathResult:
    """Create or overwrite a file. Works for tree and fixed sections.

    This OVERWRITES the entire file. To preserve existing content, read the file
    first, merge changes, then write back. Frontmatter is auto-stamped.

    For fixed sections (me/): only valid pages can be written.
    For tree sections (projects/): parent directory must already exist.

    Args:
        path: File path ending in .md (e.g. "me/now.md", "projects/acme/notes.md").
        content: The complete file content to write.

    Returns:
        {path}
    """
    mp = storage.MemoryPath.parse_file(path)
    config = storage._bootstrap[mp.section]
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
def create_directory(path: str) -> PathResult:
    """Create a directory in a tree section.

    Only creates one level — parent directory must already exist.
    Build nested structures one level at a time.

    Args:
        path: Directory path with trailing / (e.g. "projects/acme/" or "projects/acme/v2/").

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
def move_file(source: str, destination: str) -> PathResult:
    """Move or rename a file within a tree section.

    Destination directory must already exist. Does NOT update [[wikilinks]]
    in other files — read affected files and update references manually.

    Args:
        source: File path (e.g. "projects/acme/old-name.md").
        destination: File path (e.g. "projects/acme/new-name.md").

    Returns:
        {path}
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
def delete_file(path: str) -> PathResult:
    """Delete a file in any non-fixed section (tree or log).

    Cleans up empty parent directories after deletion.

    Args:
        path: File path (e.g. "projects/acme/old-notes.md", "daily/2026-03-18.md").

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
def add_log_entry(section: str, content: str) -> PathResult:
    """Append an entry to today's log in a log section.

    Creates today's log file if it doesn't exist. Content is appended as-is —
    structure the entry however you want (headings, lists, prose).

    Args:
        section: Section name (e.g. "daily").
        content: The content to append.

    Returns:
        {path}
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
def edit_log(path: str, content: str) -> PathResult:
    """Create or overwrite a log entry. Use for corrections and backfilling past dates.

    For today's log, prefer add_log_entry (appends). Use edit_log to write
    complete content for any date — past or present.

    Args:
        path: File path (e.g. "daily/2026-03-18.md").
        content: The complete file content.

    Returns:
        {path}
    """
    return storage.edit_log(storage.get_root(), path, content)


if __name__ == "__main__":
    mcp.run()
