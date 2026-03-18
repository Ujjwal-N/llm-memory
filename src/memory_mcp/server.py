"""FastMCP server: instructions, tools, resources, and prompts for the memory layer."""

from fastmcp import FastMCP

from memory_mcp import storage

INSTRUCTIONS = """\
You are connected to a personal memory layer stored as markdown files.

WORKFLOWS:
- When the user reports something they did, learned, or decided: call add_daily_entry \
with a topic. Cross-reference related projects with [[wikilinks]].
- When the user's focus or priorities change: also update me/now.md via update_me.
- Before updating any me/ page or editing a daily log: read it first to preserve \
existing content, merge your changes, then write back the complete content.
- After any structural change in projects/ (file creates, moves, deletes): call \
scan_schema to refresh your map.

SECTIONS — each has its own tools:
- me/ — Fixed set of living documents (now, about, conventions, goals, health). Use \
update_me to update. Cannot create, delete, or move. "Updated:" date is auto-stamped.
- daily/ — Flat, append-only logs. One file per day. Use add_daily_entry to log new \
entries. Use edit_daily_log only to correct existing entries.
- projects/ — Dynamic structure. Use write_project_file, move_project_file, and \
delete_project_file to manage files and directories freely.

WIKILINKS: Use [[slug]] to reference other files. [[project-slug]] for project _index, \
[[project/topic]] for nested content, [[YYYY-MM-DD]] for daily logs, [[now]] or \
[[conventions]] for me/ pages. Always add wikilinks when referencing related content.\
"""

mcp = FastMCP("memory", instructions=INSTRUCTIONS)


# --- Resources ---


@mcp.resource(
    "memory://me/{page}",
    description="Read a global context page: now, about, conventions, goals, or health.",
    annotations={"readOnlyHint": True},
)
def read_me_page(page: str) -> str:
    """Read a page from the me/ directory."""
    return storage.read_file(storage.get_root(), f"me/{page}")


@mcp.resource(
    "memory://daily/{date}",
    description="Read a daily log by date (YYYY-MM-DD format).",
    annotations={"readOnlyHint": True},
)
def read_daily(date: str) -> str:
    """Read a daily log entry by its date."""
    return storage.read_file(storage.get_root(), f"daily/{date}")


@mcp.resource(
    "memory://file/{path}",
    description="Read any file by its relative path (without .md). "
    "For directories, reads the _index.md within that directory.",
    annotations={"readOnlyHint": True},
)
def read_any_file(path: str) -> str:
    """Read any markdown file in the memory directory by relative path."""
    return storage.read_file(storage.get_root(), path)


# --- Read-only Tools ---


@mcp.tool(annotations={"readOnlyHint": True})
def scan_schema(path: str | None = None) -> dict:
    """Scan the memory directory and return a structured tree of all files.

    Returns me/ pages, project tree (recursively nested), and 20 most recent
    daily logs, each with file sizes and last-modified timestamps.

    Use at session start to understand the full directory layout. Call again
    after any structural changes in projects/.

    Args:
        path: Optional subdirectory to scope the scan (e.g. "projects/chessclaw").
              Omit to scan the entire memory directory.

    Returns:
        Full scan: {me: [...], projects: <tree>, daily_logs: [...], total_files: int}
        Scoped scan: {path: str, tree: [...]}
    """
    return storage.scan_schema(storage.get_root(), path)


# --- ME Tools ---


@mcp.tool
def update_me(page: str, content: str) -> dict:
    """Update a me/ page. Overwrites the entire page content.

    These are living documents — read the page first (via memory://me/{page}),
    merge your changes with existing content, then write back the complete page.
    The "Updated: YYYY-MM-DD" date is auto-stamped on every write.

    Args:
        page: Page name — one of: now, about, conventions, goals, health.
        content: The complete markdown content for the page.

    Returns:
        {page, full_content} or {page, error} if the page name is invalid.
    """
    return storage.update_me_page(storage.get_root(), page, content)


# --- DAILY Tools ---


@mcp.tool
def add_daily_entry(content: str, topic: str | None = None) -> dict:
    """Add a timestamped entry to today's daily log.

    Creates today's log file if it doesn't exist. Each entry gets a
    ## HH:MM or ## HH:MM — {topic} section header.

    Args:
        content: The markdown content of the entry.
        topic: Optional topic label for the section header (e.g. "ChessClaw", "Chess").

    Returns:
        {date, entry_added, full_content}
    """
    return storage.add_daily_entry(storage.get_root(), content, topic)


@mcp.tool
def edit_daily_log(date: str, content: str) -> dict:
    """Overwrite the full content of a daily log for corrections.

    Read the log first via memory://daily/{date}, make your changes, then
    write back the complete content. Only use this to correct or reorganize
    existing entries — use add_daily_entry for new entries.

    Args:
        date: The date of the log to edit (YYYY-MM-DD format).
        content: The complete markdown content for that day's log.

    Returns:
        {date, full_content} or {date, error} if no log exists for that date.
    """
    return storage.edit_daily_log(storage.get_root(), date, content)


# --- PROJECTS Tools ---


@mcp.tool
def write_project_file(path: str, content: str) -> dict:
    """Create or overwrite a file under projects/.

    This OVERWRITES the entire file. To preserve existing content, read the file
    first (via memory://file/projects/{path}), merge changes, then write back.

    Auto-creates intermediate directories and _index.md for new directories.

    Args:
        path: Path relative to projects/ (e.g. "chessclaw/v1/features").
        content: The complete markdown content to write.

    Returns:
        {path, full_content, created_directories: [str]}
    """
    return storage.write_project_file(storage.get_root(), path, content)


@mcp.tool
def move_project_file(source: str, destination: str) -> dict:
    """Move or rename a file within projects/.

    Does NOT update [[wikilinks]] in other files — you must read affected files
    and update their references manually after moving.

    Args:
        source: Current path relative to projects/ (e.g. "chessclaw/old-name").
        destination: New path relative to projects/ (e.g. "chessclaw/new-name").

    Returns:
        {old_path, new_path, success: bool, reason?: str}
    """
    return storage.move_project_file(storage.get_root(), source, destination)


@mcp.tool(annotations={"destructiveHint": True})
def delete_project_file(path: str) -> dict:
    """Delete a file under projects/.

    Refuses to delete _index.md if the directory still contains other files —
    delete or move those first. Cleans up empty parent directories after deletion.

    Args:
        path: Path relative to projects/ (e.g. "chessclaw/old-notes").

    Returns:
        {path, deleted: bool, reason: str}
    """
    return storage.delete_project_file(storage.get_root(), path)


if __name__ == "__main__":
    mcp.run()
