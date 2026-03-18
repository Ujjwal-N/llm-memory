"""File I/O operations for the memory layer: read, write, scan, move, delete."""

import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import frontmatter

# File conventions
FILE_EXT = ".md"
INDEX_FILE = f"_index{FILE_EXT}"
MD_PATTERN = f"*{FILE_EXT}"

# Top-level directory names
DIR_ME = "me"
DIR_DAILY = "daily"
DIR_PROJECTS = "projects"
TOP_LEVEL_DIRS = (DIR_ME, DIR_DAILY, DIR_PROJECTS)

# me/ — fixed page set
ME_PAGES = frozenset(("now", "about", "conventions", "goals", "health"))

# Frontmatter schemas — fields auto-managed per section
ME_FRONTMATTER = ("updated", "links")
DAILY_FRONTMATTER = ("date", "links")
PROJECTS_FRONTMATTER = ("updated", "links")

# Regex for extracting wikilinks
_WIKILINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")


# --- Frontmatter utilities ---


def _make_post(content: str, metadata: dict[str, str | list[str]]) -> str:
    """Create markdown text with YAML frontmatter."""
    post = frontmatter.Post(content)
    post.metadata.update(metadata)
    return frontmatter.dumps(post)


def _extract_wikilinks(content: str) -> list[str]:
    """Extract deduplicated, sorted [[wikilink]] slugs from markdown content."""
    return sorted(set(_WIKILINK_RE.findall(content)))


def _stamp_metadata(text: str, section: str) -> str:
    """Apply section-specific frontmatter to markdown text.

    Fields managed per section:
    - me/: updated, links (auto-extracted wikilinks)
    - daily/: date, links (auto-extracted wikilinks)
    - projects/: updated, links (auto-extracted wikilinks)
    """
    schema = {
        DIR_ME: ME_FRONTMATTER,
        DIR_DAILY: DAILY_FRONTMATTER,
        DIR_PROJECTS: PROJECTS_FRONTMATTER,
    }.get(section, ())

    post = frontmatter.loads(text)
    today = datetime.now().strftime("%Y-%m-%d")

    if "updated" in schema:
        post["updated"] = today
    if "links" in schema:
        post["links"] = _extract_wikilinks(post.content)
    if "date" in schema and "date" not in post.metadata:
        post["date"] = today

    return frontmatter.dumps(post)


# --- Core path utilities ---


def _require_section(rel_path: str) -> str:
    """Validate that a path starts with a known section. Returns the section name."""
    section = rel_path.split("/")[0]
    if section not in TOP_LEVEL_DIRS:
        raise ValueError(
            f"Path must be under {', '.join(TOP_LEVEL_DIRS)}/. Got: {rel_path}"
        )
    return section


def get_root() -> Path:
    """Resolve the memory directory root from MEMORY_DIR env var or default to ~/memory."""
    return (
        Path(os.environ.get("MEMORY_DIR", Path.home() / "memory"))
        .expanduser()
        .resolve()
    )


def _safe_resolve(root: Path, rel_path: str) -> Path:
    """Resolve a relative path to an .md file within root, preventing directory traversal."""
    full = (root / f"{rel_path}{FILE_EXT}").resolve()
    if not full.is_relative_to(root):
        raise ValueError(f"Path escapes memory directory: {rel_path}")
    return full


def _safe_resolve_dir(root: Path, rel_path: str) -> Path:
    """Resolve a relative path to a directory within root, preventing directory traversal."""
    full = (root / rel_path).resolve()
    if not full.is_relative_to(root):
        raise ValueError(f"Path escapes memory directory: {rel_path}")
    return full


# --- Init ---


def init_memory_dir(root: Path) -> dict:
    """Create the base memory directory structure if it doesn't exist.

    Creates me/, daily/, projects/ and seeds me/ with starter pages.
    Safe to run repeatedly — only creates what's missing.
    Raises SystemExit with a clear message if the root path is invalid.
    """
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SystemExit(f"Cannot create memory directory at {root}: {e}") from e

    if not root.is_dir():
        raise SystemExit(f"Memory path exists but is not a directory: {root}")

    created: list[str] = []

    for d in TOP_LEVEL_DIRS:
        target = root / d
        if not target.exists():
            target.mkdir(parents=True)
            created.append(d)

    created_files: list[str] = []
    today = datetime.now().strftime("%Y-%m-%d")
    for page in sorted(ME_PAGES):
        target = _safe_resolve(root, f"{DIR_ME}/{page}")
        if not target.exists():
            content = _make_post(f"# {page.title()}\n", {"updated": today})
            target.write_text(content)
            created_files.append(f"{DIR_ME}/{page}")

    return {
        "root": str(root),
        "created_directories": created,
        "seeded_files": created_files,
    }


# --- Read ---


def read_file(root: Path, rel_path: str) -> str:
    """Read a markdown file by relative path (without .md extension).

    Path must be under me/, daily/, or projects/.
    For directory paths, reads _index.md within that directory.
    Returns file content or a descriptive error string if not found.
    """
    _require_section(rel_path)
    target = _safe_resolve(root, rel_path)

    if target.is_file():
        return target.read_text()

    index = target.with_suffix("") / INDEX_FILE
    if index.is_file():
        return index.read_text()

    return f"Error: File not found at {rel_path}{FILE_EXT} (also checked {rel_path}/{INDEX_FILE})"


# --- Scan ---


def _file_meta(path: Path) -> dict:
    """Return size and last-modified metadata for a file."""
    stat = path.stat()
    return {
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def _scan_tree(directory: Path) -> list[dict]:
    """Recursively build a tree of files and subdirectories."""
    entries: list[dict] = []
    for child in sorted(directory.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            entries.append(
                {
                    "name": child.name,
                    "type": "directory",
                    "children": _scan_tree(child),
                }
            )
        elif child.suffix == FILE_EXT:
            entries.append(
                {
                    "name": child.name,
                    "type": "file",
                    **_file_meta(child),
                }
            )
    return entries


def scan_schema(root: Path, sub_path: str | None = None) -> dict:
    """Walk the memory directory and return a structured tree.

    Returns me/ files, project tree (recursive), and 20 most recent daily logs.
    If sub_path is given, scans only that subdirectory.
    """
    if sub_path:
        _require_section(sub_path)
        target = _safe_resolve_dir(root, sub_path)
        if not target.is_dir():
            return {"error": f"Not a directory: {sub_path}"}
        return {"path": sub_path, "tree": _scan_tree(target)}

    result: dict = {DIR_ME: [], DIR_PROJECTS: [], "daily_logs": [], "total_files": 0}

    me_dir = root / DIR_ME
    if me_dir.is_dir():
        for f in sorted(me_dir.glob(MD_PATTERN)):
            result[DIR_ME].append({"name": f.stem, **_file_meta(f)})

    projects_dir = root / DIR_PROJECTS
    if projects_dir.is_dir():
        result[DIR_PROJECTS] = _scan_tree(projects_dir)

    daily_dir = root / DIR_DAILY
    if daily_dir.is_dir():
        logs = sorted(daily_dir.glob(MD_PATTERN), reverse=True)[:20]
        for f in logs:
            result["daily_logs"].append(
                {"date": f.stem, "size_bytes": f.stat().st_size}
            )

    result["total_files"] = len(list(root.rglob(MD_PATTERN)))

    return result


# --- ME section ---


def update_me_page(root: Path, page: str, content: str) -> dict:
    """Update a me/ page. Auto-stamps frontmatter with updated date.

    Only accepts pages from the fixed set: now, about, conventions, goals, health.
    """
    if page not in ME_PAGES:
        valid = ", ".join(sorted(ME_PAGES))
        return {"page": page, "error": f"Unknown page. Valid pages: {valid}"}

    content = _stamp_metadata(content, DIR_ME)
    target = _safe_resolve(root, f"{DIR_ME}/{page}")
    target.write_text(content)
    return {"page": page, "full_content": target.read_text()}


# --- DAILY section ---


def add_daily_entry(root: Path, content: str, topic: str | None = None) -> dict:
    """Append a timestamped entry to today's daily log.

    Creates today's log file if it doesn't exist.
    Auto-updates frontmatter with wikilinks after appending.
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    daily_dir = root / DIR_DAILY
    daily_dir.mkdir(parents=True, exist_ok=True)
    target = daily_dir / f"{date_str}{FILE_EXT}"

    if not target.exists():
        initial = _make_post(f"# {date_str}\n", {"date": date_str, "links": []})
        target.write_text(initial)

    header = f"## {time_str} — {topic}" if topic else f"## {time_str}"
    entry = f"\n{header}\n{content}\n"

    with target.open("a") as f:
        f.write(entry)

    # Re-read, update frontmatter with extracted links, write back
    full_text = target.read_text()
    full_text = _stamp_metadata(full_text, DIR_DAILY)
    target.write_text(full_text)

    return {
        "date": date_str,
        "entry_added": entry.strip(),
        "full_content": target.read_text(),
    }


def edit_daily_log(root: Path, date: str, content: str) -> dict:
    """Overwrite the full content of a daily log by date.

    Auto-updates frontmatter with wikilinks.
    """
    target = _safe_resolve(root, f"{DIR_DAILY}/{date}")

    if not target.is_file():
        return {"date": date, "error": f"No daily log found for {date}."}

    content = _stamp_metadata(content, DIR_DAILY)
    target.write_text(content)
    return {"date": date, "full_content": target.read_text()}


# --- PROJECTS section ---


def write_project_file(root: Path, path: str, content: str) -> dict:
    """Create or overwrite a file under projects/.

    Auto-creates intermediate directories and _index.md for new directories.
    Auto-stamps frontmatter with updated date and extracted wikilinks.
    Path is relative to projects/ (e.g. "chessclaw/v1/features").
    """
    rel_path = f"{DIR_PROJECTS}/{path}"
    target = _safe_resolve(root, rel_path)
    projects_dir = root / DIR_PROJECTS

    created_dirs: list[str] = []
    parent = target.parent
    dirs_to_create: list[Path] = []
    while not parent.exists():
        dirs_to_create.append(parent)
        parent = parent.parent
    for d in reversed(dirs_to_create):
        d.mkdir()
        created_dirs.append(str(d.relative_to(projects_dir)))

    content = _stamp_metadata(content, DIR_PROJECTS)
    target.write_text(content)

    if target.name != INDEX_FILE:
        for d in dirs_to_create:
            if d.is_relative_to(projects_dir):
                index = d / INDEX_FILE
                if not index.exists():
                    dir_title = d.name.replace("-", " ").replace("_", " ").title()
                    index.write_text(f"# {dir_title}\n")

    return {
        "path": path,
        "full_content": target.read_text(),
        "created_directories": created_dirs,
    }


def move_project_file(root: Path, source: str, destination: str) -> dict:
    """Move or rename a file within projects/. Does not update wikilinks.

    Paths are relative to projects/ (e.g. "chessclaw/old-name").
    """
    src = _safe_resolve(root, f"{DIR_PROJECTS}/{source}")
    dst = _safe_resolve(root, f"{DIR_PROJECTS}/{destination}")

    if not src.is_file():
        return {
            "old_path": source,
            "new_path": destination,
            "success": False,
            "reason": f"Source not found: {source}{FILE_EXT}",
        }

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))

    return {"old_path": source, "new_path": destination, "success": True}


def delete_project_file(root: Path, path: str) -> dict:
    """Delete a file under projects/.

    Refuses to delete _index.md if the directory still contains other files.
    Cleans up empty parent directories after deletion.
    """
    rel_path = f"{DIR_PROJECTS}/{path}"
    target = _safe_resolve(root, rel_path)

    if not target.is_file():
        return {
            "path": path,
            "deleted": False,
            "reason": f"File not found: {path}{FILE_EXT}",
        }

    if target.name == INDEX_FILE:
        siblings = [p for p in target.parent.iterdir() if p != target]
        if siblings:
            return {
                "path": path,
                "deleted": False,
                "reason": "Cannot delete _index.md: directory still contains other files. "
                "Delete or move those first.",
            }

    target.unlink()

    projects_dir = root / DIR_PROJECTS
    parent = target.parent
    while parent != projects_dir and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent

    return {"path": path, "deleted": True, "reason": "Deleted successfully."}
