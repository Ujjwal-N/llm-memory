"""File I/O operations for the memory layer: read, write, scan, move, delete."""

import json
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from zoneinfo import ZoneInfo

import frontmatter

# Timezone for dates (log filenames, frontmatter timestamps)
_TZ = ZoneInfo(os.environ.get("MEMORY_TZ", "America/Los_Angeles"))

# File conventions
FILE_EXT = ".md"
INDEX_FILE = f"_index{FILE_EXT}"
MD_PATTERN = f"*{FILE_EXT}"

# Top-level directory names
DIR_ME = "me"
DIR_DAILY = "daily"
DIR_PROJECTS = "projects"

# Base frontmatter applied to ALL sections
BASE_FRONTMATTER = ("updated", "links")


class Behavior(StrEnum):
    """Section behavior types.

    - FIXED: immutable set of pages (valid_files required). No create/delete/move.
    - LOG: flat, append-only dated files. Supports delete. No move.
    - TREE: free-form file hierarchy. Supports create/delete/move.
    """

    FIXED = "fixed"
    LOG = "log"
    TREE = "tree"


@dataclass(frozen=True)
class SectionConfig:
    """Rules for a top-level memory section."""

    behavior: Behavior
    description: str
    extra_frontmatter: tuple[str, ...] = ()
    valid_files: frozenset[str] | None = None  # required for fixed behavior


DEFAULT_SECTIONS: dict[str, SectionConfig] = {
    DIR_ME: SectionConfig(
        behavior=Behavior.FIXED,
        description="Fixed set of living documents: now, about, conventions, goals.",
        valid_files=frozenset(("now", "about", "conventions", "goals")),
    ),
    DIR_DAILY: SectionConfig(
        behavior=Behavior.LOG,
        description="Append-only daily logs, one file per day.",
        extra_frontmatter=("date",),
    ),
    DIR_PROJECTS: SectionConfig(
        behavior=Behavior.TREE,
        description="Free-form project hierarchy with arbitrary nesting.",
    ),
}

_sections: dict[str, SectionConfig] = dict(DEFAULT_SECTIONS)

# Regex for extracting wikilinks
_WIKILINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")

_VALID_BEHAVIORS: frozenset[str] = frozenset(Behavior)


# --- Section loading ---


def _parse_sections_json(raw: str) -> dict[str, SectionConfig]:
    """Parse MEMORY_SECTIONS JSON into SectionConfig objects.

    Expected format: {"name": {"behavior": "tree", "description": "...", ...}}
    Only behavior and description are required; other fields have defaults per behavior.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"MEMORY_SECTIONS is not valid JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("MEMORY_SECTIONS must be a JSON object")

    sections: dict[str, SectionConfig] = {}
    for name, cfg in data.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"Section '{name}' must be a JSON object")
        if not name or not name.isidentifier():
            raise ValueError(
                f"Section name must be a valid identifier (letters, digits, underscores). Got: '{name}'"
            )
        if name in DEFAULT_SECTIONS:
            raise ValueError(
                f"Cannot override default section '{name}' via MEMORY_SECTIONS"
            )

        behavior = cfg.get("behavior")
        if behavior not in _VALID_BEHAVIORS:
            raise ValueError(
                f"Section '{name}': behavior must be one of {sorted(_VALID_BEHAVIORS)}, got '{behavior}'"
            )

        description = cfg.get("description")
        if not description:
            raise ValueError(f"Section '{name}': description is required")

        valid_files_raw = cfg.get("valid_files")
        valid_files = frozenset(valid_files_raw) if valid_files_raw else None

        if behavior == Behavior.FIXED and not valid_files:
            raise ValueError(f"Section '{name}': fixed behavior requires valid_files")
        if valid_files:
            for f in valid_files:
                if not f or "/" in f:
                    raise ValueError(
                        f"Section '{name}': valid_files entry '{f}' must be a "
                        f"simple name (no slashes or empty strings)."
                    )

        extra_fm = cfg.get("extra_frontmatter")
        if extra_fm:
            unknown = set(extra_fm) - set(_FRONTMATTER_HANDLERS)
            if unknown:
                raise ValueError(
                    f"Section '{name}': unknown extra_frontmatter fields {sorted(unknown)}. "
                    f"Registered handlers: {sorted(_FRONTMATTER_HANDLERS)}"
                )
        extra = tuple(extra_fm) if extra_fm else ()
        if behavior == Behavior.LOG and "date" not in extra:
            extra = ("date", *extra)

        sections[name] = SectionConfig(
            behavior=Behavior(behavior),
            description=description,
            extra_frontmatter=extra,
            valid_files=valid_files,
        )

    return sections


def load_sections() -> dict[str, SectionConfig]:
    """Load sections from DEFAULT_SECTIONS + MEMORY_SECTIONS env var.

    Returns DEFAULT_SECTIONS merged with any custom sections from the env var.
    """
    raw = os.environ.get("MEMORY_SECTIONS")
    if not raw:
        return dict(DEFAULT_SECTIONS)
    custom = _parse_sections_json(raw)
    return DEFAULT_SECTIONS | custom


def apply_sections(sections: dict[str, SectionConfig]) -> None:
    """Update module-level _sections dict in-place."""
    _sections.clear()
    _sections.update(sections)


# --- Section guide ---


def _describe_one(name: str, config: SectionConfig) -> dict:
    """Build the guide dict for a single section."""
    result: dict = {
        "name": name,
        "behavior": str(config.behavior),
        "description": config.description,
    }
    if config.valid_files:
        result["valid_files"] = sorted(f"{name}/{f}" for f in config.valid_files)
    return result


def describe_section(section: str | None = None) -> list[dict] | dict:
    """Return section guide(s). No arg = all sections. With arg = single section."""
    if section is None:
        return [_describe_one(name, cfg) for name, cfg in _sections.items()]
    config = _sections.get(section)
    if config is None:
        raise ValueError(
            f"Unknown section: '{section}'. Available: {', '.join(_sections)}"
        )
    return _describe_one(section, config)


# --- Path wrapper ---


@dataclass(frozen=True)
class MemoryPath:
    """A validated, section-prefixed path in the memory directory.

    Always has the form "{section}/{subpath}" where section is one of
    the configured top-level directories.
    """

    section: str
    subpath: str

    def __str__(self) -> str:
        return f"{self.section}/{self.subpath}"

    @classmethod
    def parse(cls, path: str) -> "MemoryPath":
        """Parse a section-prefixed path string like 'me/now' or 'projects/acme/features'."""
        parts = path.split("/", 1)
        if len(parts) < 2 or not parts[1]:
            raise ValueError(f"Path must be {{section}}/{{subpath}}. Got: {path}")
        if parts[0] not in _sections:
            raise ValueError(
                f"Path must start with {', '.join(_sections)}/. Got: {path}"
            )
        return cls(section=parts[0], subpath=parts[1])

    def resolve_file(self, root: Path) -> Path:
        """Resolve to an absolute .md file path within root, preventing directory traversal."""
        full = (root / f"{self}{FILE_EXT}").resolve()
        if not full.is_relative_to(root):
            raise ValueError(f"Path escapes memory directory: {self}")
        return full

    def resolve_dir(self, root: Path) -> Path:
        """Resolve to an absolute directory path within root, preventing directory traversal."""
        full = (root / str(self)).resolve()
        if not full.is_relative_to(root):
            raise ValueError(f"Path escapes memory directory: {self}")
        return full


# --- Frontmatter utilities ---


def _extract_wikilinks(content: str) -> list[str]:
    """Extract deduplicated, sorted [[wikilink]] slugs from markdown content."""
    return sorted(set(_WIKILINK_RE.findall(content)))


# --- Frontmatter handler registry ---

type FrontmatterHandler = Callable[[frontmatter.Post, str], None]


def _stamp_updated(post: frontmatter.Post, today: str) -> None:
    post["updated"] = today


def _stamp_links(post: frontmatter.Post, _today: str) -> None:
    post["links"] = _extract_wikilinks(post.content)


def _stamp_date(post: frontmatter.Post, today: str) -> None:
    post.metadata.setdefault("date", today)


_FRONTMATTER_HANDLERS: dict[str, FrontmatterHandler] = {
    "updated": _stamp_updated,
    "links": _stamp_links,
    "date": _stamp_date,
}


def _stamp_metadata(text: str, section: str) -> str:
    """Apply frontmatter fields from BASE_FRONTMATTER + section's extra_frontmatter.

    Each field is resolved via _FRONTMATTER_HANDLERS registry.
    """
    config = _sections.get(section)
    if config is None:
        return text

    post = frontmatter.loads(text)
    today = datetime.now(tz=_TZ).strftime("%Y-%m-%d")

    for field in BASE_FRONTMATTER + config.extra_frontmatter:
        _FRONTMATTER_HANDLERS[field](post, today)

    return frontmatter.dumps(post)


# --- Core path utilities ---


DEFAULT_MEMORY_DIR = Path.cwd() / "memory"


def get_root() -> Path:
    """Resolve the memory directory root from MEMORY_DIR env var or ./memory in the current working directory."""
    return Path(os.environ.get("MEMORY_DIR", DEFAULT_MEMORY_DIR)).expanduser().resolve()


# --- Init ---


def _seed_file(path: Path, title: str, section: str) -> None:
    """Write a starter markdown file with a heading and stamped frontmatter."""
    content = _stamp_metadata(f"# {title}\n", section)
    path.write_text(content)


def init_memory_dir(root: Path) -> dict:
    """Create the base memory directory structure if it doesn't exist.

    Creates directories for all configured sections and seeds fixed sections with starter pages.
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

    for d in _sections:
        target = root / d
        if not target.exists():
            target.mkdir(parents=True)
            created.append(d)

    created_files: list[str] = []
    for section_name, config in _sections.items():
        if config.behavior == Behavior.FIXED and not config.valid_files:
            raise SystemExit(
                f"Section '{section_name}' has fixed behavior but no valid_files."
            )
        if config.behavior == Behavior.FIXED and config.valid_files:
            for page in sorted(config.valid_files):
                mp = MemoryPath(section_name, page)
                target = mp.resolve_file(root)
                if not target.exists():
                    _seed_file(target, page.title(), section_name)
                    created_files.append(str(mp))

    return {
        "root": str(root),
        "created_directories": created,
        "seeded_files": created_files,
    }


# --- Read ---


def read_file(root: Path, path: str) -> str:
    """Read a markdown file by section-prefixed path (without .md extension).

    For directory paths, reads _index.md within that directory.
    """
    mp = MemoryPath.parse(path)
    target = mp.resolve_file(root)

    if target.is_file():
        return target.read_text()

    index = target.with_suffix("") / INDEX_FILE
    if index.is_file():
        return index.read_text()

    raise ValueError(f"File not found: {mp}{FILE_EXT} (also checked {mp}/{INDEX_FILE})")


# --- Scan ---


def _file_modified(path: Path) -> str:
    """Return last-modified timestamp for a file."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _scan_tree(directory: Path, base_path: str) -> list[dict]:
    """Recursively build a tree of files and subdirectories.

    base_path is the full path to this directory (e.g. "projects/acme").
    """
    entries: list[dict] = []
    for child in sorted(directory.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            child_path = f"{base_path}/{child.name}"
            entries.append(
                {
                    "type": "directory",
                    "path": child_path,
                    "children": _scan_tree(child, child_path),
                }
            )
        elif child.suffix == FILE_EXT:
            entries.append(
                {
                    "type": "file",
                    "path": f"{base_path}/{child.stem}",
                    "modified": _file_modified(child),
                }
            )
    return entries


def _scan_fixed(directory: Path, section_name: str) -> list[dict]:
    """Scan a fixed-behavior section: flat file list."""
    if not directory.is_dir():
        return []
    return [
        {"path": f"{section_name}/{f.stem}", "modified": _file_modified(f)}
        for f in sorted(directory.glob(MD_PATTERN))
    ]


def _scan_log(directory: Path, section_name: str, limit: int = 20) -> list[dict]:
    """Scan a log-behavior section: most recent N files, reverse sorted."""
    if not directory.is_dir():
        return []
    return [
        {"path": f"{section_name}/{f.stem}", "modified": _file_modified(f)}
        for f in sorted(directory.glob(MD_PATTERN), reverse=True)[:limit]
    ]


def _scan_section(
    directory: Path, section_name: str, config: SectionConfig
) -> list[dict]:
    """Dispatch to the appropriate scanner based on section behavior."""
    if not directory.is_dir():
        return []
    if config.behavior == Behavior.FIXED:
        return _scan_fixed(directory, section_name)
    if config.behavior == Behavior.LOG:
        return _scan_log(directory, section_name)
    return _scan_tree(directory, section_name)


def scan_schema(root: Path, sub_path: str | None = None) -> dict:
    """Walk the memory directory and return a structured schema.

    Every file entry includes a full path usable with read_file and a modified timestamp.
    Tree sections additionally include type (file/directory) and nested children.
    If sub_path is given, scans only that subdirectory.
    """
    if sub_path:
        # Bare section name (e.g. "projects") — scan entire section
        if "/" not in sub_path:
            if sub_path not in _sections:
                raise ValueError(
                    f"Unknown section: '{sub_path}'. Available: {', '.join(_sections)}"
                )
            section_dir = root / sub_path
            config = _sections[sub_path]
            return {
                "path": sub_path,
                "entries": _scan_section(section_dir, sub_path, config),
            }

        # Subdirectory scan (e.g. "projects/acme")
        mp = MemoryPath.parse(sub_path)
        target = mp.resolve_dir(root)
        if not target.is_dir():
            raise ValueError(f"Not a directory: {mp}")
        return {"path": str(mp), "tree": _scan_tree(target, str(mp))}

    result: dict = {}
    for section_name, config in _sections.items():
        result[section_name] = _scan_section(root / section_name, section_name, config)
    return result


def _check_behavior(section: str, expected: Behavior) -> None:
    """Assert section has the expected behavior. Violation indicates a routing bug."""
    config = _sections.get(section)
    if config is None or config.behavior != expected:
        actual = config.behavior if config else "unknown"
        raise RuntimeError(
            f"Internal error: '{section}' has behavior '{actual}', "
            f"expected {expected}. This is a bug in tool routing."
        )


# --- FIXED section (generic) ---


def update_fixed_page(root: Path, path: str, content: str) -> dict:
    """Update a page in a fixed-behavior section. Auto-stamps frontmatter."""
    mp = MemoryPath.parse(path)
    _check_behavior(mp.section, Behavior.FIXED)
    config = _sections[mp.section]
    if config.valid_files and mp.subpath not in config.valid_files:
        valid = ", ".join(f"{mp.section}/{f}" for f in sorted(config.valid_files))
        raise ValueError(f"Invalid page '{mp}'. Valid pages: {valid}.")

    content = _stamp_metadata(content, mp.section)
    target = mp.resolve_file(root)
    target.write_text(content)
    return {"path": str(mp), "full_content": target.read_text()}


# --- LOG section (generic) ---


def add_log_entry(root: Path, section: str, content: str) -> dict:
    """Append an entry to today's log in the given section."""
    _check_behavior(section, Behavior.LOG)
    date_str = datetime.now(tz=_TZ).strftime("%Y-%m-%d")
    mp = MemoryPath(section, date_str)
    target = mp.resolve_file(root)
    target.parent.mkdir(exist_ok=True)

    if not target.exists():
        _seed_file(target, date_str, section)

    with target.open("a") as f:
        f.write(content)

    full_text = target.read_text()
    full_text = _stamp_metadata(full_text, section)
    target.write_text(full_text)

    return {
        "path": str(mp),
        "full_content": target.read_text(),
    }


def edit_log(root: Path, path: str, content: str) -> dict:
    """Overwrite the full content of a log entry by full path."""
    mp = MemoryPath.parse(path)
    _check_behavior(mp.section, Behavior.LOG)
    target = mp.resolve_file(root)

    if not target.is_file():
        raise ValueError(
            f"No log found at {mp}. Use add_log_entry to create a new one."
        )

    content = _stamp_metadata(content, mp.section)
    target.write_text(content)
    return {"path": str(mp), "full_content": target.read_text()}


# --- TREE section (generic) ---


def _check_parent_exists(parent: Path, section: str, root: Path) -> None:
    """Raise if a parent directory doesn't exist."""
    if not parent.exists():
        parent_rel = parent.relative_to(root / section)
        raise ValueError(
            f"Directory does not exist: {section}/{parent_rel}. "
            f"Use create_directory to create it first."
        )


def create_directory(root: Path, path: str) -> dict:
    """Create a directory in a tree-behavior section.

    Only creates one level — parent must already exist.
    """
    mp = MemoryPath.parse(path)
    _check_behavior(mp.section, Behavior.TREE)
    target = mp.resolve_dir(root)

    if target.exists():
        raise ValueError(f"Directory already exists: {mp}")

    _check_parent_exists(target.parent, mp.section, root)
    target.mkdir()
    return {"path": str(mp)}


def write_tree_file(root: Path, path: str, content: str) -> dict:
    """Create or overwrite a file in a tree-behavior section.

    Parent directory must already exist — use create_directory first.
    """
    mp = MemoryPath.parse(path)
    _check_behavior(mp.section, Behavior.TREE)
    target = mp.resolve_file(root)

    _check_parent_exists(target.parent, mp.section, root)

    content = _stamp_metadata(content, mp.section)
    target.write_text(content)

    return {
        "path": str(mp),
        "full_content": target.read_text(),
    }


def move_tree_file(root: Path, source: str, destination: str) -> dict:
    """Move or rename a file within a tree-behavior section."""
    src_mp = MemoryPath.parse(source)
    _check_behavior(src_mp.section, Behavior.TREE)
    dst_mp = MemoryPath.parse(destination)
    dst_config = _sections.get(dst_mp.section)
    if dst_config is None or dst_config.behavior != Behavior.TREE:
        raise ValueError(
            f"Cannot move files into '{dst_mp.section}/' — only tree sections support moves."
        )
    src = src_mp.resolve_file(root)
    dst = dst_mp.resolve_file(root)

    if not src.is_file():
        raise ValueError(
            f"Source not found: {src_mp}{FILE_EXT}. Use scan_schema to find valid paths."
        )
    if dst.is_file():
        raise ValueError(f"Destination already exists: {dst_mp}{FILE_EXT}")

    _check_parent_exists(dst.parent, dst_mp.section, root)
    shutil.move(str(src), str(dst))

    return {
        "path": str(dst_mp),
        "full_content": dst.read_text(),
    }


def delete_file(root: Path, path: str) -> dict:
    """Delete a file in any non-fixed section.

    Refuses to delete _index.md if the directory still contains other files.
    Cleans up empty parent directories after deletion.
    """
    mp = MemoryPath.parse(path)
    config = _sections.get(mp.section)
    if config is None or config.behavior == Behavior.FIXED:
        raise ValueError(f"Cannot delete files in '{mp.section}' section.")
    target = mp.resolve_file(root)

    if not target.is_file():
        raise ValueError(
            f"File not found: {mp}{FILE_EXT}. Use scan_schema to find valid paths."
        )

    if target.name == INDEX_FILE:
        siblings = [p for p in target.parent.iterdir() if p != target]
        if siblings:
            raise ValueError(
                "Cannot delete _index.md while directory contains other files. "
                "Delete or move those first."
            )

    target.unlink()

    section_dir = root / mp.section
    parent = target.parent
    while parent != section_dir and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent

    return {"path": str(mp)}
